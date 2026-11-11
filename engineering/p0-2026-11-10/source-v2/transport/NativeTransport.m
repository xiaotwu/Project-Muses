// MIT. P0 direct HTTP range transport. No JS media objects or persistent caches.
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#include <mach/mach.h>
#include <stdatomic.h>
#include <pthread.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <TargetConditionals.h>
#include "muses_transport.h"

typedef struct { uint64_t begin, end; } MTInterval;
@interface MTReader : NSObject <NSURLSessionDataDelegate, NSURLSessionTaskDelegate> {
@public
    MTLimits limits; MTStats stats; MTAuthorizeURL authorize; void *policyContext;
    NSString *url; NSDictionary *headers; double expiry;
    NSURLSession *session; NSURLSessionDataTask *active;
    NSLock *operation, *control; pthread_mutex_t mutex; atomic_bool cancelled;
    dispatch_semaphore_t completion; NSMutableData *buffer;
    uint64_t blockStart, blockEnd, expectedLength, knownTotal, declaredTotal;
    NSString *validator; BOOL accepted, completed;
    MTInterval intervals[512]; size_t intervalCount;
}
- (MTStatus)readAt:(uint64_t)offset output:(void *)output capacity:(size_t)capacity received:(size_t *)received;
- (void)cancel;
- (BOOL)permits:(NSURL *)candidate;
- (void)fail:(MTStatus)status;
@end

static uint64_t residentBytes(void) {
    mach_task_basic_info_data_t info; mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    return task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &count) == KERN_SUCCESS ? info.resident_size : UINT64_MAX;
}
static MTRetry retryFor(MTStatus code) {
    if (code == MT_URL_EXPIRED) return MT_RETRY_FRESH_DESCRIPTOR;
    if (code == MT_NETWORK_ERROR || code == MT_TIMEOUT) return MT_RETRY_NETWORK;
    if (code == MT_KIND_UNSUPPORTED || code == MT_RANGE_UNSUPPORTED) return MT_RETRY_DIFFERENT_CAPABILITY;
    return MT_RETRY_NONE;
}
static void setStatus(MTReader *r, MTStatus status) { r->stats.status = status; r->stats.retry = retryFor(status); }

@implementation MTReader
- (instancetype)init {
    if ((self = [super init])) { pthread_mutex_init(&mutex, NULL); atomic_init(&cancelled, false); operation = [NSLock new]; control = [NSLock new]; buffer = [NSMutableData new]; }
    return self;
}
- (void)dealloc { pthread_mutex_destroy(&mutex); }
- (BOOL)permits:(NSURL *)candidate {
    if (!candidate || candidate.user.length || candidate.password.length || !candidate.host.length) return NO;
    BOOL secure = [candidate.scheme.lowercaseString isEqualToString:@"https"];
#ifdef MT_TESTING
    BOOL local = limits.allow_test_loopback && [candidate.scheme.lowercaseString isEqualToString:@"http"] &&
        ([candidate.host isEqualToString:@"127.0.0.1"] || [candidate.host isEqualToString:@"::1"]);
#else
    BOOL local = NO;
#endif
    return (secure || local) && authorize && authorize(candidate.absoluteString.UTF8String, policyContext);
}
- (void)fail:(MTStatus)status {
    setStatus(self, status);
    if (!completed) { completed = YES; dispatch_semaphore_signal(completion); }
}
- (void)cancel {
    atomic_store(&cancelled, true);
    pthread_mutex_lock(&mutex);
    [active cancel];
    pthread_mutex_unlock(&mutex);
}
- (void)URLSession:(NSURLSession *)s task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *))handler {
    // Redirect credentials/Range inheritance is not an implemented capability.
    // Call the host policy even for redirects, then fail closed without logging.
    pthread_mutex_lock(&mutex);
    if (task == active) { BOOL allowed = [self permits:request.URL]; [self fail:allowed ? MT_RANGE_UNSUPPORTED : MT_URL_POLICY]; }
    pthread_mutex_unlock(&mutex); handler(nil);
}
- (void)URLSession:(NSURLSession *)s task:(NSURLSessionTask *)task didReceiveChallenge:(NSURLAuthenticationChallenge *)challenge completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition, NSURLCredential *))handler {
    if ([challenge.protectionSpace.authenticationMethod isEqualToString:NSURLAuthenticationMethodServerTrust]) { handler(NSURLSessionAuthChallengePerformDefaultHandling,nil); return; }
    pthread_mutex_lock(&mutex); if(task==active)[self fail:MT_AUTH_REQUIRED]; pthread_mutex_unlock(&mutex);
    handler(NSURLSessionAuthChallengeCancelAuthenticationChallenge,nil);
}
- (void)URLSession:(NSURLSession *)s dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response completionHandler:(void (^)(NSURLSessionResponseDisposition))handler {
    pthread_mutex_lock(&mutex);
    if (task != active || atomic_load(&cancelled)) { pthread_mutex_unlock(&mutex); handler(NSURLSessionResponseCancel); return; }
    NSHTTPURLResponse *http = [response isKindOfClass:NSHTTPURLResponse.class] ? (id)response : nil;
    stats.responses++; stats.http_status = (uint32_t)http.statusCode;
    MTStatus status = MT_OK;
    uint64_t total = 0, length = 0;
    NSString *encoding = [http valueForHTTPHeaderField:@"Content-Encoding"];
    NSString *tag = [http valueForHTTPHeaderField:@"ETag"];
    if (!http) status = MT_NETWORK_ERROR;
    else if (http.statusCode == 401) status = MT_AUTH_REQUIRED;
    else if (http.statusCode == 403 || http.statusCode == 410)
        status = expiry > 0 && NSDate.date.timeIntervalSince1970 >= expiry ? MT_URL_EXPIRED : MT_HTTP_FORBIDDEN;
    else if (encoding.length && ![encoding.lowercaseString isEqualToString:@"identity"]) status = MT_RANGE_INVALID;
    else if (http.statusCode == 206) {
        NSString *range = [http valueForHTTPHeaderField:@"Content-Range"];
        unsigned long long begin = 0, end = 0, size = 0; int used = 0;
        const char *raw = range.UTF8String;
        if (!raw || range.length > 128 || sscanf(raw, "bytes %llu-%llu/%llu%n", &begin, &end, &size, &used) != 3 || used != strlen(raw) ||
            begin != blockStart || end < begin || end > blockEnd || size <= end) status = MT_RANGE_INVALID;
        else { total = size; length = end - begin + 1; stats.range_supported = 1; }
    } else if (http.statusCode == 200) {
        if (validator.length) status = MT_CONTENT_CHANGED;
        else if (blockStart != 0 || response.expectedContentLength < 0 || (uint64_t)response.expectedContentLength > limits.block_bytes) status = MT_RANGE_UNSUPPORTED;
        else { total = length = response.expectedContentLength; stats.range_supported = 0; }
    } else status = MT_HTTP_STATUS;
    if (status == MT_OK && (total == 0 || total > limits.media_limit_bytes || length > limits.block_bytes)) status = MT_RESOURCE_LIMIT;
    if (status == MT_OK && knownTotal && total != knownTotal) status = MT_CONTENT_CHANGED;
    if (status == MT_OK && declaredTotal && total != declaredTotal) status = MT_CONTENT_CHANGED;
    if (status == MT_OK && response.expectedContentLength >= 0 && (uint64_t)response.expectedContentLength != length) status = MT_RANGE_INVALID;
    if (status == MT_OK && validator.length && (!tag || ![validator isEqualToString:tag])) status = MT_CONTENT_CHANGED;
    if (status == MT_OK) {
        NSString *type = http.MIMEType.lowercaseString;
        if ([type containsString:@"mpegurl"] || [type containsString:@"text/html"] || [type containsString:@"application/json"]) status = MT_KIND_UNSUPPORTED;
    }
    if (status == MT_OK) { knownTotal = total; stats.total_bytes = total; expectedLength = length; if (!validator && tag.length) validator = [tag copy]; accepted = YES; }
    else [self fail:status];
    pthread_mutex_unlock(&mutex);
    handler(status == MT_OK ? NSURLSessionResponseAllow : NSURLSessionResponseCancel);
}
- (void)URLSession:(NSURLSession *)s dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
    pthread_mutex_lock(&mutex);
    if (task == active && accepted && !completed) {
        stats.network_bytes += data.length;
        stats.resident_high_bytes = MAX(stats.resident_high_bytes, residentBytes());
        if (atomic_load(&cancelled)) { [self fail:MT_CANCELLED]; [task cancel]; }
        else if (stats.network_bytes > limits.network_limit_bytes || buffer.length + data.length > expectedLength || stats.resident_high_bytes > limits.process_rss_limit_bytes) {
            [self fail:MT_RESOURCE_LIMIT]; [task cancel];
        } else { [buffer appendData:data]; stats.buffer_high_bytes = MAX(stats.buffer_high_bytes, buffer.length); }
    }
    pthread_mutex_unlock(&mutex);
}
- (void)URLSession:(NSURLSession *)s task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
    pthread_mutex_lock(&mutex);
    if (task == active && !completed) {
        MTStatus status = atomic_load(&cancelled) ? MT_CANCELLED : MT_OK;
        if (status == MT_OK && error) status = error.code == NSURLErrorTimedOut ? MT_TIMEOUT : MT_NETWORK_ERROR;
        if (status == MT_OK && (!accepted || buffer.length != expectedLength)) status = MT_TRUNCATED;
        [self fail:status];
    }
    pthread_mutex_unlock(&mutex);
}
- (void)addInterval:(uint64_t)begin end:(uint64_t)end {
    MTInterval merged = { begin, end }; size_t output = 0;
    for (size_t i = 0; i < intervalCount; ++i) {
        if (intervals[i].end < merged.begin || intervals[i].begin > merged.end) intervals[output++] = intervals[i];
        else { merged.begin = MIN(merged.begin, intervals[i].begin); merged.end = MAX(merged.end, intervals[i].end); }
    }
    intervals[output++] = merged; intervalCount = output;
    stats.unique_validated_bytes = 0;
    for (size_t i = 0; i < intervalCount; ++i) stats.unique_validated_bytes += intervals[i].end - intervals[i].begin;
}
- (MTStatus)readAt:(uint64_t)offset output:(void *)output capacity:(size_t)capacity received:(size_t *)received {
    *received = 0;
    if (![operation tryLock]) return MT_BUSY;
    pthread_mutex_lock(&mutex);
    MTStatus result = MT_OK;
    if (atomic_load(&cancelled)) result = MT_CANCELLED;
    else if (knownTotal && offset >= knownTotal) result = MT_EOF;
    else if (accepted && completed && stats.status == MT_OK && offset >= blockStart && offset < blockStart + buffer.length) {
        size_t count = MIN(capacity, buffer.length - (size_t)(offset - blockStart));
        memcpy(output, (const uint8_t *)buffer.bytes + offset - blockStart, count); *received = count; stats.delivered_bytes += count;
        pthread_mutex_unlock(&mutex); [operation unlock]; return MT_OK;
    } else if (offset >= limits.media_limit_bytes || stats.requests >= limits.maximum_requests || stats.network_bytes >= limits.network_limit_bytes) result = MT_RESOURCE_LIMIT;
    else if (expiry > 0 && NSDate.date.timeIntervalSince1970 >= expiry) result = MT_URL_EXPIRED;
    if (result != MT_OK) { setStatus(self, result); pthread_mutex_unlock(&mutex); [operation unlock]; return result; }
    blockStart = offset; blockEnd = MIN(limits.media_limit_bytes - 1, offset + limits.block_bytes - 1);
    blockEnd = MIN(blockEnd, offset + limits.network_limit_bytes - stats.network_bytes - 1);
    if (knownTotal) blockEnd = MIN(blockEnd, knownTotal-1);
    accepted = NO; completed = NO; expectedLength = 0; [buffer setLength:0];
    completion = dispatch_semaphore_create(0); setStatus(self, MT_OK); stats.requests++;
    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:[NSURL URLWithString:url]];
    request.timeoutInterval = limits.request_timeout_ms / 1000.0;
    request.cachePolicy = NSURLRequestReloadIgnoringLocalCacheData;
    request.allHTTPHeaderFields = headers;
    [request setValue:@"identity" forHTTPHeaderField:@"Accept-Encoding"];
    [request setValue:[NSString stringWithFormat:@"bytes=%llu-%llu", blockStart, blockEnd] forHTTPHeaderField:@"Range"];
    if (validator.length && ![validator hasPrefix:@"W/"]) [request setValue:validator forHTTPHeaderField:@"If-Range"];
    active = [session dataTaskWithRequest:request]; [active resume];
    pthread_mutex_unlock(&mutex);
    long timedOut = dispatch_semaphore_wait(completion, dispatch_time(DISPATCH_TIME_NOW, ((int64_t)limits.request_timeout_ms+500)*NSEC_PER_MSEC));
    pthread_mutex_lock(&mutex);
    if (timedOut) { [active cancel]; setStatus(self, MT_TIMEOUT); }
    result = stats.status;
    if (result == MT_OK) {
        [self addInterval:blockStart end:blockStart+buffer.length];
        size_t count = MIN(capacity, buffer.length); memcpy(output, buffer.bytes, count); *received = count; stats.delivered_bytes += count;
    } else { accepted = NO; [buffer setLength:0]; }
    active = nil;
    pthread_mutex_unlock(&mutex); [operation unlock]; return result;
}
@end

MTHandle *mt_create(const MTDescriptor *d, const MTLimits *l, MTAuthorizeURL authorize, void *context, MTStatus *status) {
    if (status) *status = MT_BAD_DESCRIPTOR;
    if (!d || !l || !d->url || d->abi_version != 1 || !authorize || d->header_count > 8 || (d->header_count && !d->headers) || strlen(d->url)>16384 ||
        !l->media_limit_bytes || l->media_limit_bytes>16ull*1024*1024 || !l->network_limit_bytes || l->network_limit_bytes>16ull*1024*1024 ||
        l->block_bytes<4096 || l->block_bytes>262144 || !l->maximum_requests || l->maximum_requests>512 || l->request_timeout_ms<100 || l->request_timeout_ms>15000 ||
        !l->process_rss_limit_bytes || l->process_rss_limit_bytes>256ull*1024*1024 ||
        d->content_length_hint>l->media_limit_bytes) return NULL;
    if (d->kind != MT_DIRECT) { if (status) *status = MT_KIND_UNSUPPORTED; return NULL; }
    MTReader *r = [MTReader new]; r->limits = *l; r->authorize = authorize; r->policyContext = context; r->expiry = d->expires_unix_seconds;
    r->declaredTotal = d->content_length_hint;
    r->url = [NSString stringWithUTF8String:d->url];
    if (!r->url) return NULL;
    if (![r permits:[NSURL URLWithString:r->url]]) { if (status) *status=MT_URL_POLICY; return NULL; }
    NSMutableDictionary *headers = [NSMutableDictionary new]; size_t headerBytes = 0;
    NSSet *allowed = [NSSet setWithArray:@[@"user-agent",@"accept",@"accept-language",@"origin",@"referer",@"dnt"]];
    for (uint32_t i=0;i<d->header_count;++i) {
        if (!d->headers[i].name || !d->headers[i].value) return NULL;
        NSString *name = [NSString stringWithUTF8String:d->headers[i].name], *value = [NSString stringWithUTF8String:d->headers[i].value];
        headerBytes += strlen(d->headers[i].name)+strlen(d->headers[i].value);
        if (headerBytes>4096 || ![allowed containsObject:name.lowercaseString] || [value rangeOfCharacterFromSet:NSCharacterSet.newlineCharacterSet].location != NSNotFound) return NULL;
        headers[name]=value;
    }
    r->headers = headers;
    NSURLSessionConfiguration *config = NSURLSessionConfiguration.ephemeralSessionConfiguration;
    config.URLCache = nil; config.HTTPCookieStorage = nil; config.URLCredentialStorage = nil;
    config.HTTPShouldSetCookies = NO; config.HTTPMaximumConnectionsPerHost = 1;
    config.requestCachePolicy = NSURLRequestReloadIgnoringLocalCacheData;
    NSOperationQueue *queue = [NSOperationQueue new]; queue.maxConcurrentOperationCount = 1;
    r->session = [NSURLSession sessionWithConfiguration:config delegate:r delegateQueue:queue];
    if (status) *status = MT_OK;
    return (__bridge_retained MTHandle *)r;
}
MTStatus mt_read_at(MTHandle *h, uint64_t offset, void *output, size_t capacity, size_t *received) {
    if (!h || !output || !received || !capacity) return MT_BAD_DESCRIPTOR;
    @autoreleasepool { MTReader *r=(__bridge MTReader *)h; if(![r->control tryLock]){*received=0;return MT_BUSY;} MTStatus status=[r readAt:offset output:output capacity:capacity received:received];[r->control unlock];return status; }
}
MTStatus mt_snapshot(MTHandle *h, MTStats *out) {
    if (!h || !out) return MT_BAD_DESCRIPTOR;
    MTReader *r=(__bridge MTReader *)h; pthread_mutex_lock(&r->mutex); *out=r->stats; pthread_mutex_unlock(&r->mutex); return MT_OK;
}
void mt_cancel(MTHandle *h) { if (h) [(__bridge MTReader *)h cancel]; }
void mt_destroy(MTHandle *h) {
    if (!h) return;
    MTReader *r=(__bridge_transfer MTReader *)h; [r cancel]; [r->session invalidateAndCancel]; r->session=nil;
}
MTStatus mt_copy_to_file(MTHandle *h, const char *destination, MTProgress progress, void *context) {
    if (!h || !destination || destination[0]!='/') return MT_BAD_DESCRIPTOR;
    MTReader *r=(__bridge MTReader *)h;
    NSString *path=[NSString stringWithUTF8String:destination], *partial=[path stringByAppendingString:@".partial"];
    struct stat st; if (!lstat(destination,&st) || !lstat(partial.fileSystemRepresentation,&st)) return MT_DESTINATION_ERROR;
    uint8_t *bytes=malloc(r->limits.block_bytes); if (!bytes) return MT_RESOURCE_LIMIT;
    if(![r->control tryLock]){free(bytes);return MT_BUSY;}
    MTStatus result=MT_OK; uint64_t offset=0; int fd=-1; CC_SHA256_CTX digest; CC_SHA256_Init(&digest);
    for (;;) {
        size_t got=0; result=[r readAt:offset output:bytes capacity:r->limits.block_bytes received:&got];
        if (result==MT_EOF) { result=MT_OK; break; }
        if (result!=MT_OK || got==0) { if (result==MT_OK) result=MT_TRUNCATED; break; }
        if (fd<0) {
#if TARGET_OS_IPHONE
            // Select protection at creation, before any bytes are written while
            // locked. Do not assume a directory's protection is inherited.
            NSError *creationError=nil;
            NSDataWritingOptions options=NSDataWritingWithoutOverwriting|NSDataWritingFileProtectionCompleteUntilFirstUserAuthentication;
            if (![[NSData data] writeToFile:partial options:options error:&creationError]) {result=MT_DESTINATION_ERROR;break;}
            fd=open(partial.fileSystemRepresentation,O_WRONLY|O_NOFOLLOW);
            struct stat created;
            if (fd>=0 && (fstat(fd,&created)!=0 || !S_ISREG(created.st_mode) || created.st_size!=0 || fchmod(fd,0600)!=0)) {
                close(fd);fd=-1;
            }
            NSDictionary *attributes=[[NSFileManager defaultManager] attributesOfItemAtPath:partial error:nil];
            if (fd>=0 && ![attributes[NSFileProtectionKey] isEqual:NSFileProtectionCompleteUntilFirstUserAuthentication]) {close(fd);fd=-1;}
#else
            fd=open(partial.fileSystemRepresentation,O_CREAT|O_EXCL|O_WRONLY|O_NOFOLLOW,0600);
#endif
        }
        if (fd<0) { result=MT_DESTINATION_ERROR; break; }
        size_t written=0;
        while (written<got) { ssize_t n=write(fd,bytes+written,got-written); if(n<=0){result=MT_DESTINATION_ERROR;break;} written+=(size_t)n; }
        if (result!=MT_OK) break;
        CC_SHA256_Update(&digest,bytes,(CC_LONG)got); offset+=got;
        if(progress){MTStats snapshot;mt_snapshot(h,&snapshot);progress(&snapshot,context);}
    }
    free(bytes);
    if(fd>=0){if(fsync(fd)!=0 && result==MT_OK)result=MT_DESTINATION_ERROR;close(fd);}
    pthread_mutex_lock(&r->mutex);
    if(result==MT_OK && (offset!=r->knownTotal || !offset || r->stats.unique_validated_bytes!=r->knownTotal))result=MT_TRUNCATED;
    if(result==MT_OK && renamex_np(partial.fileSystemRepresentation,destination,RENAME_EXCL)!=0)result=MT_DESTINATION_ERROR;
    if(result==MT_OK){unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256_Final(hash,&digest);for(int i=0;i<32;i++)snprintf(r->stats.sha256+i*2,3,"%02x",hash[i]);r->stats.complete_file=1;}
    setStatus(r,result);pthread_mutex_unlock(&r->mutex);[r->control unlock];return result;
}
const char *mt_status_name(MTStatus status) {
    switch(status){case MT_OK:return "ok";case MT_EOF:return "eof";case MT_CANCELLED:return "cancelled";case MT_BAD_DESCRIPTOR:return "bad_descriptor";case MT_KIND_UNSUPPORTED:return "kind_unsupported";case MT_URL_POLICY:return "url_policy";case MT_HTTP_FORBIDDEN:return "http_forbidden";case MT_URL_EXPIRED:return "url_expired";case MT_AUTH_REQUIRED:return "auth_required";case MT_RANGE_UNSUPPORTED:return "range_unsupported";case MT_RANGE_INVALID:return "range_invalid";case MT_CONTENT_CHANGED:return "content_changed";case MT_RESOURCE_LIMIT:return "resource_limit";case MT_NETWORK_ERROR:return "network_error";case MT_TIMEOUT:return "timeout";case MT_TRUNCATED:return "truncated";case MT_DESTINATION_ERROR:return "destination_error";case MT_BUSY:return "busy";default:return "http_status";}
}
