// MIT. Independent P0 feasibility harness; not production code.
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <mach/mach_time.h>
#import <sys/resource.h>
#include "quickjs.h"
#include <time.h>
// SPDX-License-Identifier: MIT
// Included once in the Objective-C native host, after its system includes.
#ifndef P0_V2_NATIVE_CONTROL_INCLUDED
#define P0_V2_NATIVE_CONTROL_INCLUDED
#import <Foundation/Foundation.h>
#include <mach/mach.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <time.h>
#include "transport/muses_transport.h"

enum { V2_REASON_NONE=0, V2_REASON_CANCELLED=1, V2_REASON_DEADLINE=2,
       V2_REASON_RSS=3, V2_REASON_RSS_UNAVAILABLE=4,
       V2_REASON_WATCHDOG_UNAVAILABLE=5, V2_REASON_TRANSFER_BINDING=6 };
enum { V2_CONTROL_IDLE=0, V2_CONTROL_RUNNING=1, V2_CONTROL_ENDING=2 };
static const uint64_t V2_RSS_LIMIT = 256ull * 1024 * 1024;
static const uint64_t V2_SAMPLE_NS = 100000000ull;
static pthread_mutex_t V2ControlMutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t V2ControlWake = PTHREAD_COND_INITIALIZER;
static int V2ControlPhase;
static uint64_t V2LastGeneration, V2WatchGeneration;
static pthread_t V2WatchThread;
static bool V2WatchCreated, V2TransferCancelled;
static MTHandle *V2CurrentTransfer;
static _Atomic(uint64_t) V2ActiveGeneration, V2DeadlineNS, V2NextRSSNS, V2PeakRSS;
static atomic_int V2Reason;
static _Thread_local uint64_t V2OwnerGeneration;

#ifdef P0_V2_CONTROL_TESTING
// Deterministic local harness only; production always uses Mach/monotonic time.
static uint64_t P0V2TestNowNS(void);
static bool P0V2TestReadRSS(uint64_t *bytes);
#endif
static uint64_t P0V2ClockNS(void) {
#ifdef P0_V2_CONTROL_TESTING
    return P0V2TestNowNS();
#else
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return UINT64_MAX;
    return (uint64_t)value.tv_sec * 1000000000ull + (uint64_t)value.tv_nsec;
#endif
}
static bool P0V2ReadRSS(uint64_t *bytes) {
#ifdef P0_V2_CONTROL_TESTING
    return P0V2TestReadRSS(bytes);
#else
    mach_task_basic_info_data_t info;
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return false;
    *bytes = info.resident_size;
    return true;
#endif
}
static void P0V2SetStop(int reason) {
    int none = V2_REASON_NONE;
    atomic_compare_exchange_strong(&V2Reason, &none, reason);
    // Signaling without the mutex is safe: the watcher also has a 100 ms poll.
    // Never enter transport here; this path can run inside a parser/JS callback.
    pthread_cond_signal(&V2ControlWake);
}
static void P0V2Observe(uint64_t generation, bool forceRSS) {
    if (!generation || atomic_load(&V2ActiveGeneration) != generation) return;
    uint64_t now = P0V2ClockNS();
    if (now >= atomic_load(&V2DeadlineNS)) P0V2SetStop(V2_REASON_DEADLINE);
    uint64_t due = atomic_load(&V2NextRSSNS);
    if (forceRSS || (now >= due && atomic_compare_exchange_strong(&V2NextRSSNS, &due, now + V2_SAMPLE_NS))) {
        uint64_t bytes = 0;
        if (!P0V2ReadRSS(&bytes)) P0V2SetStop(V2_REASON_RSS_UNAVAILABLE);
        else {
            uint64_t old = atomic_load(&V2PeakRSS);
            while (bytes > old && !atomic_compare_exchange_weak(&V2PeakRSS, &old, bytes)) {}
            if (bytes > V2_RSS_LIMIT) P0V2SetStop(V2_REASON_RSS);
        }
    }
}
// The caller holds V2ControlMutex through mt_cancel. Therefore unbind cannot
// return while either UI cancellation or the watcher still uses this handle.
static void P0V2CancelBoundLocked(void) {
    if (V2CurrentTransfer && !V2TransferCancelled) {
        V2TransferCancelled = true;
        mt_cancel(V2CurrentTransfer);
    }
}
static void *P0V2Watch(void *argument) {
    @autoreleasepool {
        uint64_t generation = *(const uint64_t *)argument;
        pthread_mutex_lock(&V2ControlMutex);
        while (V2ControlPhase == V2_CONTROL_RUNNING && atomic_load(&V2ActiveGeneration) == generation) {
            P0V2Observe(generation, true);
            if (atomic_load(&V2Reason) != V2_REASON_NONE) {
                P0V2CancelBoundLocked();
                break;
            }
            struct timespec relative = {0, (long)V2_SAMPLE_NS};
            pthread_cond_timedwait_relative_np(&V2ControlWake, &V2ControlMutex, &relative);
        }
        pthread_mutex_unlock(&V2ControlMutex);
    }
    return NULL;
}

// Begin/End/Bind/Unbind/ShouldStop run on one serial operation worker. UI calls
// Cancel only. A false Begin (BUSY or invalid timeout) never resets active work.
bool P0V2BeginOperation(double seconds) {
    if (!isfinite(seconds) || seconds <= 0 || seconds > 180) return false;
    uint64_t now = P0V2ClockNS(), duration = (uint64_t)(seconds * 1e9);
    if (!duration || now > UINT64_MAX - duration - V2_SAMPLE_NS) return false;
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase != V2_CONTROL_IDLE) { pthread_mutex_unlock(&V2ControlMutex); return false; }
    uint64_t generation = ++V2LastGeneration;
    if (!generation) generation = ++V2LastGeneration;
    V2ControlPhase = V2_CONTROL_RUNNING;
    V2WatchGeneration = generation;
    V2CurrentTransfer = NULL;
    V2TransferCancelled = false;
    atomic_store(&V2Reason, V2_REASON_NONE);
    atomic_store(&V2PeakRSS, 0);
    atomic_store(&V2DeadlineNS, now + duration);
    atomic_store(&V2NextRSSNS, now + V2_SAMPLE_NS);
    atomic_store(&V2ActiveGeneration, generation);
    V2OwnerGeneration = generation;
    P0V2Observe(generation, true);
    int error = pthread_create(&V2WatchThread, NULL, P0V2Watch, &V2WatchGeneration);
    V2WatchCreated = error == 0;
    if (error) {
        P0V2SetStop(V2_REASON_WATCHDOG_UNAVAILABLE);
        atomic_store(&V2ActiveGeneration, 0);
        V2OwnerGeneration = 0;
        V2ControlPhase = V2_CONTROL_IDLE;
    }
    pthread_mutex_unlock(&V2ControlMutex);
    return !error;
}
void P0V2Cancel(void) {
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase == V2_CONTROL_RUNNING) {
        P0V2SetStop(V2_REASON_CANCELLED);
        P0V2CancelBoundLocked();
    }
    pthread_mutex_unlock(&V2ControlMutex);
}
int V2ShouldStop(void) {
    uint64_t generation = V2OwnerGeneration;
    if (!generation || atomic_load(&V2ActiveGeneration) != generation) return 1;
    P0V2Observe(generation, false);
    return atomic_load(&V2Reason) != V2_REASON_NONE;
}
void V2BindTransfer(MTHandle *handle) {
    if (!handle) return;
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase != V2_CONTROL_RUNNING || !V2OwnerGeneration || atomic_load(&V2ActiveGeneration) != V2OwnerGeneration) {
        mt_cancel(handle); // Fail closed; never attach a stale worker's handle.
    } else if (V2CurrentTransfer && V2CurrentTransfer != handle) {
        P0V2SetStop(V2_REASON_TRANSFER_BINDING);
        P0V2CancelBoundLocked();
        mt_cancel(handle);
    } else {
        V2CurrentTransfer = handle;
        if (atomic_load(&V2Reason) != V2_REASON_NONE) P0V2CancelBoundLocked();
    }
    pthread_mutex_unlock(&V2ControlMutex);
}
void V2UnbindTransfer(MTHandle *handle) {
    pthread_mutex_lock(&V2ControlMutex);
    if (V2OwnerGeneration && atomic_load(&V2ActiveGeneration) == V2OwnerGeneration && V2CurrentTransfer == handle) {
        V2CurrentTransfer = NULL;
        V2TransferCancelled = false;
    }
    pthread_mutex_unlock(&V2ControlMutex);
}
void P0V2EndOperation(void) {
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase != V2_CONTROL_RUNNING || !V2OwnerGeneration || atomic_load(&V2ActiveGeneration) != V2OwnerGeneration) {
        pthread_mutex_unlock(&V2ControlMutex);
        return;
    }
    V2ControlPhase = V2_CONTROL_ENDING;
    atomic_store(&V2ActiveGeneration, 0);
    // Defensive cancellation; the owner must still join media work before
    // destroying any handle. End never destroys a caller-owned transport.
    P0V2CancelBoundLocked();
    V2CurrentTransfer = NULL;
    V2TransferCancelled = false;
    pthread_cond_signal(&V2ControlWake);
    bool join = V2WatchCreated;
    pthread_t thread = V2WatchThread;
    pthread_mutex_unlock(&V2ControlMutex);
    if (join) pthread_join(thread, NULL);
    pthread_mutex_lock(&V2ControlMutex);
    V2WatchCreated = false;
    V2ControlPhase = V2_CONTROL_IDLE;
    V2OwnerGeneration = 0;
    pthread_mutex_unlock(&V2ControlMutex);
}
NSString *V2StopReason(void) {
    switch (atomic_load(&V2Reason)) {
        case V2_REASON_NONE: return @"none";
        case V2_REASON_CANCELLED: return @"cancelled";
        case V2_REASON_DEADLINE: return @"deadline";
        case V2_REASON_RSS: return @"rss_limit";
        case V2_REASON_RSS_UNAVAILABLE: return @"rss_observer_unavailable";
        case V2_REASON_WATCHDOG_UNAVAILABLE: return @"watchdog_unavailable";
        case V2_REASON_TRANSFER_BINDING: return @"transfer_binding";
        default: return @"unknown";
    }
}
uint64_t V2ObservedPeakRSS(void) { return atomic_load(&V2PeakRSS); }
#endif


static double Now(void) { return NSProcessInfo.processInfo.systemUptime; }
static JSRuntime *runtime;
static JSContext *context;
static double deadline;
static BOOL finished;
static int resultCode;
static uint64_t maxBody = 4 * 1024 * 1024;
static NSString *mediaDirectory;
static void (^mediaHandler)(NSString *,BOOL);
static void (^logHandler)(NSString *);
static NSString *activeMode;
static NSUInteger storedMediaBytes;
void P0SetMediaDirectory(NSString *directory) {mediaDirectory=[directory copy];}
void P0SetMediaHandler(void (^handler)(NSString *,BOOL)) {mediaHandler=[handler copy];}
void P0SetLogHandler(void (^handler)(NSString *)) {logHandler=[handler copy];}
static void Output(NSString *line){puts(line.UTF8String);fflush(stdout);if(logHandler)logHandler(line);}
static size_t peakAllocated;
typedef struct { size_t size; size_t alignment; } AllocationHeader;
static size_t AllocationSize(const void *p) { return p ? ((const AllocationHeader *)p)[-1].size : 0; }
static void *Allocate(JSMallocState *s,size_t n) {
    size_t total=n+sizeof(AllocationHeader); if(total<n || total>s->malloc_limit-s->malloc_size)return NULL;
    AllocationHeader *p=malloc(total);if(!p)return NULL;p->size=n;s->malloc_size+=total;s->malloc_count++;peakAllocated=MAX(peakAllocated,s->malloc_size);return p+1;
}
static void Release(JSMallocState *s,void *ptr) {if(!ptr)return;AllocationHeader *p=(AllocationHeader *)ptr-1;s->malloc_size-=p->size+sizeof(*p);s->malloc_count--;free(p);}
static void *Resize(JSMallocState *s,void *ptr,size_t n) {if(!ptr)return Allocate(s,n);if(!n){Release(s,ptr);return NULL;}AllocationHeader *old=(AllocationHeader *)ptr-1;size_t oldSize=old->size,total=n+sizeof(*old);if(total<n || n>s->malloc_limit-s->malloc_size+oldSize)return NULL;AllocationHeader *p=realloc(old,total);if(!p)return NULL;p->size=n;s->malloc_size=s->malloc_size-oldSize+n;peakAllocated=MAX(peakAllocated,s->malloc_size);return p+1;}
static const JSMallocFunctions Allocator={Allocate,Release,Resize,AllocationSize};
static NSString *JSONString(id obj) {
    NSData *data = [NSJSONSerialization dataWithJSONObject:obj options:0 error:nil];
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
}
static NSString *String(JSContext *ctx, JSValueConst value) {
    const char *s = JS_ToCString(ctx, value);
    NSString *result = s ? [NSString stringWithUTF8String:s] : @"";
    JS_FreeCString(ctx, s); return result;
}
static JSValue JSString(JSContext *ctx, NSString *s) { return JS_NewString(ctx, s.UTF8String ?: ""); }
static BOOL Allowed(NSURL *url) {
    NSString *h = url.host.lowercaseString;
    return [url.scheme isEqual:@"https"] && ([h isEqual:@"youtube.com"] || [h hasSuffix:@".youtube.com"]);
}
@interface Bridge : NSObject <NSURLSessionDataDelegate>
@property NSURLSession *session;
@property NSMutableDictionary<NSNumber *, NSMutableDictionary *> *requests;
@property NSMutableArray<NSDictionary *> *events;
@property NSMutableDictionary<NSNumber *, NSDictionary *> *timers;
@property NSUInteger requestCount;
@property NSUInteger receivedBytes;
@property NSUInteger peakConcurrent;
@property NSUInteger firstByteCount;
@property NSMutableArray<NSNumber *> *firstByteMS;
- (void)enqueue:(NSDictionary *)event;
@end
@implementation Bridge
- (instancetype)init {
    if ((self = [super init])) {
        _requests = [NSMutableDictionary dictionary]; _events = [NSMutableArray array]; _timers = [NSMutableDictionary dictionary]; _firstByteMS = [NSMutableArray array];
        NSURLSessionConfiguration *config = NSURLSessionConfiguration.ephemeralSessionConfiguration;
        config.HTTPCookieStorage = nil; config.HTTPShouldSetCookies = NO; config.URLCache = nil;
        config.timeoutIntervalForRequest = 20; config.timeoutIntervalForResource = 25;
        config.HTTPMaximumConnectionsPerHost = 4;
        NSOperationQueue *queue = [[NSOperationQueue alloc] init]; queue.maxConcurrentOperationCount = 1;
        _session = [NSURLSession sessionWithConfiguration:config delegate:self delegateQueue:queue];
    } return self;
}
- (void)enqueue:(NSDictionary *)event { @synchronized(self) { [_events addObject:event]; } }
- (void)URLSession:(NSURLSession *)s task:(NSURLSessionTask *)task willPerformHTTPRedirection:(NSHTTPURLResponse *)response newRequest:(NSURLRequest *)request completionHandler:(void (^)(NSURLRequest *))handler { handler(Allowed(request.URL) ? request : nil); }
- (void)URLSession:(NSURLSession *)s dataTask:(NSURLSessionDataTask *)task didReceiveResponse:(NSURLResponse *)response completionHandler:(void (^)(NSURLSessionResponseDisposition))handler {
    @synchronized(self) {
        NSMutableDictionary *entry = _requests[@(task.taskIdentifier)];
        entry[@"response"] = response;
        if (response.expectedContentLength >= 0 && (uint64_t)response.expectedContentLength > maxBody) { entry[@"reason"] = @"response_limit"; handler(NSURLSessionResponseCancel); return; }
    } handler(NSURLSessionResponseAllow);
}
- (void)URLSession:(NSURLSession *)s dataTask:(NSURLSessionDataTask *)task didReceiveData:(NSData *)data {
    @synchronized(self) {
        NSMutableDictionary *entry = _requests[@(task.taskIdentifier)];
        if (!entry) return;
        NSMutableData *body = entry[@"body"];
        if (!body.length) { [_firstByteMS addObject:@((Now() - [entry[@"started"] doubleValue]) * 1000)]; _firstByteCount++; }
        if (body.length + data.length > maxBody || _receivedBytes + data.length > 16*1024*1024) { entry[@"reason"] = @"response_limit"; [task cancel]; return; }
        [body appendData:data]; _receivedBytes += data.length;
    }
}
- (void)URLSession:(NSURLSession *)s task:(NSURLSessionTask *)task didCompleteWithError:(NSError *)error {
    @synchronized(self) {
        NSMutableDictionary *entry = _requests[@(task.taskIdentifier)]; if (!entry) return;
        NSHTTPURLResponse *response = entry[@"response"];
        NSString *reason = entry[@"reason"] ?: (error ? (error.code == NSURLErrorCancelled ? @"aborted" : error.code == NSURLErrorTimedOut ? @"timeout" : [NSString stringWithFormat:@"network_%ld",(long)error.code]) : @"");
        NSMutableDictionary *headers = [NSMutableDictionary dictionary];
        for (id key in response.allHeaderFields) { NSString *lower = [key lowercaseString]; if (![lower isEqual:@"set-cookie"]) headers[lower] = [response.allHeaderFields[key] description]; }
        [_events addObject:@{@"id":entry[@"id"], @"body":entry[@"body"], @"meta":@{@"status":@(response.statusCode), @"headers":headers, @"url":response.URL.absoluteString ?: @"", @"error":reason}}];
        [_requests removeObjectForKey:@(task.taskIdentifier)];
    }
}
@end
static Bridge *bridge;
static int Interrupt(JSRuntime *rt, void *opaque) { return Now() > deadline || V2ShouldStop(); }
static int ScriptInterrupt(JSRuntime *rt,void *opaque) {return Now()>*(double *)opaque || V2ShouldStop();}
NSString *P0IsolatedEvaluate(NSString *input) {
    NSString *source=[NSString stringWithFormat:@"(function(){%@})()",input];
    JSRuntime *isolated=JS_NewRuntime();if(!isolated)return nil;JS_SetMemoryLimit(isolated,8*1024*1024);JS_SetMaxStackSize(isolated,512*1024);
    double stop=Now()+1;JS_SetInterruptHandler(isolated,ScriptInterrupt,&stop);JSContext *inner=JS_NewContext(isolated);if(!inner){JS_FreeRuntime(isolated);return nil;}
    NSData *utf8=[source dataUsingEncoding:NSUTF8StringEncoding];JSValue value=JS_Eval(inner,utf8.bytes,utf8.length,"isolated-player.js",JS_EVAL_TYPE_GLOBAL);
    NSString *output=nil;
    if(JS_IsException(value)){JSValue ex=JS_GetException(inner);JS_FreeValue(inner,ex);}
    else {JSValue json=JS_JSONStringify(inner,value,JS_UNDEFINED,JS_UNDEFINED);output=String(inner,json);JS_FreeValue(inner,json);}
    JS_FreeValue(inner,value);JS_FreeContext(inner);JS_FreeRuntime(isolated);return output;
}
static JSValue NativeEval(JSContext *ctx,JSValueConst obj,int argc,JSValueConst *argv) {NSString *output=P0IsolatedEvaluate(String(ctx,argv[0]));return output?JSString(ctx,output):JS_ThrowInternalError(ctx,"isolated player evaluation failed");}
static JSValue NativePrint(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {Output(String(ctx,argv[0]));return JS_UNDEFINED;}
static JSValue NativeFinish(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) { JS_ToInt32(ctx, &resultCode, argv[0]); finished = YES; return JS_UNDEFINED; }
static JSValue NativeUUID(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) { return JSString(ctx, NSUUID.UUID.UUIDString.lowercaseString); }
static NSData *Bytes(JSContext *ctx, JSValueConst arg) {
    size_t len = 0; uint8_t *ptr = JS_GetArrayBuffer(ctx, &len, arg);
    if (ptr) return [NSData dataWithBytes:ptr length:len];
    JSValue ex = JS_GetException(ctx); JS_FreeValue(ctx, ex);
    size_t offset, bytes;
    JSValue buf = JS_GetTypedArrayBuffer(ctx, arg, &offset, &len, &bytes);
    if (JS_IsException(buf)) return nil;
    ptr = JS_GetArrayBuffer(ctx, &bytes, buf);
    NSData *data = ptr ? [NSData dataWithBytes:ptr + offset length:len] : nil;
    JS_FreeValue(ctx, buf); return data;
}
static JSValue NativeEncode(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) { NSData *d = [String(ctx, argv[0]) dataUsingEncoding:NSUTF8StringEncoding]; return JS_NewArrayBufferCopy(ctx, d.bytes, d.length); }
static JSValue NativeDecode(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) { NSData *d = Bytes(ctx, argv[0]); return JSString(ctx, [[NSString alloc] initWithData:d encoding:NSUTF8StringEncoding] ?: @""); }
static JSValue NativeStoreMedia(JSContext *ctx,JSValueConst obj,int argc,JSValueConst *argv) {
    NSData *data=Bytes(ctx,argv[0]);if(!data.length||data.length>maxBody)return JS_ThrowRangeError(ctx,"invalid bounded media");
    NSString *dir=mediaDirectory?:@"/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/media";
    [[NSFileManager defaultManager] createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:nil error:nil];
    BOOL next=[activeMode hasSuffix:@"next"];NSString *path=[dir stringByAppendingPathComponent:next?@"next.m4a":@"first.m4a"];
    BOOL reset=argc<2||JS_ToBool(ctx,argv[1]),final=argc<3||JS_ToBool(ctx,argv[2]);if(reset)storedMediaBytes=0;
    if(storedMediaBytes+data.length>maxBody)return JS_ThrowRangeError(ctx,"total media limit");
    if(reset){if(![data writeToFile:path options:NSDataWritingAtomic error:nil])return JS_ThrowInternalError(ctx,"owned media write failed");}
    else {NSFileHandle *file=[NSFileHandle fileHandleForWritingAtPath:path];if(!file)return JS_ThrowInternalError(ctx,"owned media append failed");[file seekToEndOfFile];[file writeData:data];[file closeFile];}
    storedMediaBytes+=data.length;if(final&&mediaHandler)mediaHandler(path,next);return JS_NewInt64(ctx,storedMediaBytes);
}
static JSValue NativeBase64(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    BOOL decode = JS_ToBool(ctx, argv[1]); NSString *input = String(ctx, argv[0]);
    if (decode) return JSString(ctx, [[NSString alloc] initWithData:[[NSData alloc] initWithBase64EncodedString:input options:0] encoding:NSISOLatin1StringEncoding] ?: @"");
    return JSString(ctx, [[input dataUsingEncoding:NSISOLatin1StringEncoding] base64EncodedStringWithOptions:0]);
}
static JSValue NativeSHA1(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    NSData *d = [String(ctx, argv[0]) dataUsingEncoding:NSUTF8StringEncoding]; unsigned char digest[CC_SHA1_DIGEST_LENGTH]; CC_SHA1(d.bytes, (CC_LONG)d.length, digest);
    NSMutableString *out = [NSMutableString string]; for(int i=0;i<CC_SHA1_DIGEST_LENGTH;i++) [out appendFormat:@"%02x",digest[i]]; return JSString(ctx,out);
}
static JSValue NativeURL(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    NSString *input = String(ctx, argv[0]); NSString *base = argc>1 ? String(ctx,argv[1]) : @"";
    NSURL *url = [NSURL URLWithString:input relativeToURL:base.length ? [NSURL URLWithString:base] : nil].absoluteURL;
    NSURLComponents *c = [NSURLComponents componentsWithURL:url resolvingAgainstBaseURL:YES];
    if (argc>3) {
        NSString *key=String(ctx,argv[2]), *value=String(ctx,argv[3]);
        if ([key isEqual:@"search"]) c.percentEncodedQuery = value.length>0 ? ([value hasPrefix:@"?"] ? [value substringFromIndex:1] : value) : nil;
        else if ([key isEqual:@"hash"]) c.percentEncodedFragment = value.length>0 ? ([value hasPrefix:@"#"] ? [value substringFromIndex:1] : value) : nil;
        else if ([key isEqual:@"pathname"]) c.percentEncodedPath=value;
        else if ([key isEqual:@"hostname"]) c.host=value;
        else if ([key isEqual:@"protocol"]) c.scheme=[value stringByReplacingOccurrencesOfString:@":" withString:@""];
        else if ([key isEqual:@"port"]) c.port=value.length?@([value integerValue]):nil;
    }
    if (!c.scheme.length || !c.host.length) return JS_ThrowTypeError(ctx,"Invalid URL");
    NSString *host=c.port ? [NSString stringWithFormat:@"%@:%@",c.host,c.port]:c.host;
    return JSString(ctx,JSONString(@{@"href":c.URL.absoluteString,@"protocol":[c.scheme stringByAppendingString:@":"],@"host":host,@"hostname":c.host,@"port":c.port.stringValue?:@"",@"pathname":c.percentEncodedPath.length?c.percentEncodedPath:@"/",@"search":c.percentEncodedQuery?[@"?" stringByAppendingString:c.percentEncodedQuery]:@"",@"hash":c.percentEncodedFragment?[@"#" stringByAppendingString:c.percentEncodedFragment]:@"",@"origin":[NSString stringWithFormat:@"%@://%@",c.scheme,host]}));
}
static JSValue NativeRequest(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    NSDictionary *p=[NSJSONSerialization JSONObjectWithData:[String(ctx,argv[0]) dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
    NSURL *url=[NSURL URLWithString:p[@"url"]];
    if (!Allowed(url)) return JS_ThrowTypeError(ctx,"native origin denied");
    @synchronized(bridge) {
        if (bridge.requests.count>=4 || bridge.requestCount>=32 || V2ShouldStop()) return JS_ThrowRangeError(ctx,"native concurrency limit");
        NSMutableURLRequest *request=[NSMutableURLRequest requestWithURL:url]; request.HTTPMethod=p[@"method"]?:@"GET";
        for(NSString *key in p[@"headers"]) if(![@[@"cookie",@"authorization",@"proxy-authorization"] containsObject:key.lowercaseString]) [request setValue:p[@"headers"][key] forHTTPHeaderField:key];
        if ([p[@"body"] isKindOfClass:NSString.class]) request.HTTPBody=[p[@"body"] dataUsingEncoding:NSUTF8StringEncoding];
        if (request.HTTPBody.length > 1024*1024) return JS_ThrowRangeError(ctx,"native request limit");
        NSURLSessionDataTask *task=[bridge.session dataTaskWithRequest:request];
        bridge.requests[@(task.taskIdentifier)]=[@{@"id":p[@"id"],@"task":task,@"body":[NSMutableData data],@"started":@(Now())} mutableCopy];
        bridge.requestCount++; bridge.peakConcurrent=MAX(bridge.peakConcurrent,bridge.requests.count);
        [task resume];
    } return JS_UNDEFINED;
}
static JSValue NativeCancel(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    int64_t value; JS_ToInt64(ctx,&value,argv[0]);
    @synchronized(bridge) { for (NSMutableDictionary *entry in bridge.requests.allValues) if ([entry[@"id"] longLongValue]==value) [entry[@"task"] cancel]; } return JS_UNDEFINED;
}
static JSValue NativeTimer(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    int64_t n; double ms; JS_ToInt64(ctx,&n,argv[0]); JS_ToFloat64(ctx,&ms,argv[1]);
    if(ms>=0 && bridge.timers.count>=128 && !bridge.timers[@(n)])return JS_ThrowRangeError(ctx,"native timer limit");
    if (ms<0) [bridge.timers removeObjectForKey:@(n)]; else bridge.timers[@(n)]=@{@"id":@(n),@"due":@(Now()+MIN(ms,60000)/1000)}; return JS_UNDEFINED;
}
static void Register(const char *name, JSCFunction *fn, int length) { JSValue g=JS_GetGlobalObject(context); JS_SetPropertyStr(context,g,name,JS_NewCFunction(context,fn,name,length)); JS_FreeValue(context,g); }
static void Error(const char *stage) {
    JSValue exception=JS_GetException(context);JS_FreeValue(context,exception);
    Output(JSONString(@{@"gate":@(stage),@"outcome":@"fail",@"category":@"runtime_exception",@"stop_reason":V2StopReason()}));
}
// MIT. Included after baseline host helpers, before RunProof.
#include "transport/muses_transport.h"
#ifndef P0_IOS
#include "transport/muses_decode_probe.h"
#endif
#include "parser/p0_parser.h"
static NSString *V2Client = @"VISIONOS";
static NSString *V2Codec = @"aac";
static NSDictionary *V2Descriptor;
static NSString *V2CompletedPath;
static NSString *V2SHA(const void *bytes, size_t length) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(bytes, (CC_LONG)length, digest);
    NSMutableString *value = [NSMutableString stringWithCapacity:64];
    for (int i=0;i<CC_SHA256_DIGEST_LENGTH;i++) [value appendFormat:@"%02x",digest[i]];
    return value;
}

static BOOL V2MediaAllowed(NSURL *url) {
    NSString *host = url.host.lowercaseString;
    return [url.scheme isEqual:@"https"] &&
        ([host isEqual:@"googlevideo.com"] || [host hasSuffix:@".googlevideo.com"] ||
         [host isEqual:@"youtube.com"] || [host hasSuffix:@".youtube.com"]);
}
static JSValue V2ReceiveDescriptor(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    if (argc != 1) return JS_ThrowTypeError(ctx, "descriptor argument count");
    NSString *serialized = String(ctx, argv[0]);
    NSData *json = [serialized dataUsingEncoding:NSUTF8StringEncoding];
    if (json.length > 32768) return JS_ThrowRangeError(ctx, "descriptor limit");
    NSDictionary *value = [NSJSONSerialization JSONObjectWithData:json options:0 error:nil];
    NSString *expectedVideo = [activeMode hasSuffix:@"_next"] ? @"eRsGyueVLvQ" : @"aqz-KE-bpKQ";
    if (![value isKindOfClass:NSDictionary.class] || [value[@"version"] integerValue] != 1 ||
        ![value[@"kind"] isEqual:@"direct"] || ![value[@"client"] isEqual:V2Client] ||
        ![value[@"codec"] isEqual:V2Codec] ||
        ![value[@"video_id"] isEqual:expectedVideo] ||
        ![value[@"url"] isKindOfClass:NSString.class] || !V2MediaAllowed([NSURL URLWithString:value[@"url"]]) ||
        ![value[@"content_length"] isKindOfClass:NSNumber.class] ||
        [value[@"content_length"] unsignedLongLongValue] == 0 || [value[@"content_length"] unsignedLongLongValue] > 16*1024*1024)
        return JS_ThrowTypeError(ctx, "invalid native descriptor");
    V2Descriptor = [value copy];
    return JS_UNDEFINED;
}
static int V2ParserCancelled(void *ignored) { return V2ShouldStop(); }
static NSDictionary *V2FilterEvent(NSDictionary *event) {
    NSDictionary *meta = event[@"meta"];
    NSURL *url = [NSURL URLWithString:meta[@"url"]];
    if ([meta[@"status"] integerValue] != 200 || ![url.path containsString:@"/s/player/"] || ![url.path hasSuffix:@"/base.js"])
        return event;
    NSData *input = event[@"body"];
    size_t capacity = 256*1024;
    char *reduced = malloc(capacity+1);
    if (!reduced) return nil;
    struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
    p0_parser_limits limits = {4*1024*1024, 64*1024*1024, capacity, 256,
        (uint64_t)now.tv_sec*1000000000+now.tv_nsec+5000000000ull, NULL};
    limits.should_cancel = V2ParserCancelled;
    p0_parser_result result = {0};
    p0_parser_status status = p0_player_reduce(input.bytes, input.length, &limits, reduced, capacity+1, &result);
    Output(JSONString(@{@"gate":@"native_player_reduce", @"outcome":status==P0_PARSE_OK?@"pass":@"fail",
        @"category":@(p0_parser_status_name(status)), @"input_bytes":@(input.length), @"output_bytes":@(result.output_bytes),
        @"player_sha256":V2SHA(input.bytes,input.length),
        @"reduced_sha256":status==P0_PARSE_OK?V2SHA(reduced,result.output_bytes):@"",
        @"native_peak_bytes":@(result.peak_working_bytes), @"native_live_after_bytes":@(result.live_working_bytes),
        @"parse_ms":@(result.parse_ns/1e6), @"reduce_ms":@(result.reduce_ns/1e6),
        @"solver_matches":@(result.solver_matches), @"timestamp_matches":@(result.timestamp_matches)}));
    if (status != P0_PARSE_OK) { free(reduced); return nil; }
    NSMutableDictionary *replaced = [event mutableCopy];
    replaced[@"body"] = [NSData dataWithBytesNoCopy:reduced length:result.output_bytes freeWhenDone:YES];
    NSMutableDictionary *newMeta = [meta mutableCopy], *headers = [meta[@"headers"] mutableCopy];
    headers[@"content-length"] = @(result.output_bytes).stringValue;
    newMeta[@"headers"] = headers; replaced[@"meta"] = newMeta;
    return replaced;
}
static int V2Authorize(const char *url, void *ignored) {
    return V2MediaAllowed([NSURL URLWithString:@(url)]);
}
static void V2Progress(const MTStats *stats, void *ignored) {
    // Bounded per-block counts only. No URL or response headers are retained.
    Output(JSONString(@{@"gate":@"native_media_progress", @"outcome":@"pass",
        @"validated_bytes":@(stats->unique_validated_bytes), @"total_bytes":@(stats->total_bytes),
        @"requests":@(stats->requests), @"buffer_high_bytes":@(stats->buffer_high_bytes)}));
}
static int V2Transfer(void) {
    if (V2ShouldStop()) return 130;
    NSDictionary *availability = V2Descriptor[@"availability"];
    if (![availability isKindOfClass:NSDictionary.class] || ![availability[@"state"] isEqual:@"known"] ||
        ![availability[@"availableAtUnixMs"] isKindOfClass:NSNumber.class] ||
        !isfinite([availability[@"availableAtUnixMs"] doubleValue])) return 2;
    double wait = MAX(0, [availability[@"availableAtUnixMs"] doubleValue]/1000.0 - NSDate.date.timeIntervalSince1970);
    if (wait > 20) {
        Output(JSONString(@{@"gate":@"native_availability", @"outcome":@"bounded_stop", @"wait_ms":@((int)(wait*1000))}));
        return 2;
    }
    double available = Now() + wait;
    while (Now() < available) {
        if (V2ShouldStop()) return 130;
        [NSThread sleepForTimeInterval:MIN(0.02, available-Now())];
    }
    NSDictionary *publicHeaders = V2Descriptor[@"headers"];
    if (![publicHeaders isKindOfClass:NSDictionary.class] || publicHeaders.count > 8) return 2;
    MTHeader headers[8]; uint32_t count = 0;
    for (NSString *name in publicHeaders) {
        if (![publicHeaders[name] isKindOfClass:NSString.class]) return 2;
        headers[count++] = (MTHeader){name.UTF8String, [publicHeaders[name] UTF8String]};
    }
    MTDescriptor descriptor = {1, MT_DIRECT, [V2Descriptor[@"url"] UTF8String], headers, count,
        [V2Descriptor[@"content_length"] unsignedLongLongValue], [V2Descriptor[@"expires_unix_seconds"] doubleValue]};
    MTLimits limits = {16*1024*1024, 16*1024*1024, 256*1024, 512, 15000, 0, 256*1024*1024};
    MTStatus status;
    MTHandle *handle = mt_create(&descriptor, &limits, V2Authorize, NULL, &status);
    if (!handle) {
        Output(JSONString(@{@"gate":@"native_media_create", @"outcome":@"fail", @"category":@(mt_status_name(status))}));
        return 1;
    }
    NSString *name = [NSString stringWithFormat:@"%@-%@-%@.%@", V2Client, V2Descriptor[@"video_id"], NSUUID.UUID.UUIDString,
        [V2Codec isEqual:@"opus"] ? @"webm" : @"m4a"];
    NSString *directory = mediaDirectory ?: @"/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/media";
    NSString *destination = [directory stringByAppendingPathComponent:name];
    double before = Now();
    V2BindTransfer(handle);
    status = mt_copy_to_file(handle, destination.fileSystemRepresentation, V2Progress, NULL);
    MTStats stats; mt_snapshot(handle, &stats); V2UnbindTransfer(handle); mt_destroy(handle);
    struct rusage usage; getrusage(RUSAGE_SELF, &usage);
    Output(JSONString(@{@"gate":@"native_media_complete", @"outcome":status==MT_OK?@"pass":@"fail",
        @"category":@(mt_status_name(status)), @"http_status":@(stats.http_status),
        @"expected_bytes":@(descriptor.content_length_hint), @"validated_bytes":@(stats.unique_validated_bytes),
        @"network_bytes":@(stats.network_bytes), @"requests":@(stats.requests),
        @"complete_file":@(stats.complete_file), @"sha256":@(stats.sha256),
        @"buffer_high_bytes":@(stats.buffer_high_bytes), @"process_maxrss_bytes":@(usage.ru_maxrss),
        @"elapsed_ms":@((Now()-before)*1000), @"owned_media_filename":name}));
    if (status != MT_OK || !stats.complete_file) return 1;
    V2CompletedPath = destination;
#ifdef P0_IOS
    NSError *protectionError = nil;
    if (![[NSFileManager defaultManager] setAttributes:@{NSFileProtectionKey:NSFileProtectionCompleteUntilFirstUserAuthentication}
        ofItemAtPath:destination error:&protectionError]) {
        Output(JSONString(@{@"gate":@"native_media_protection", @"outcome":@"fail", @"error_code":@(protectionError.code)}));
        return 1;
    }
#else
    // Each comparison gets a fresh, independently bounded handle to the exact
    // same representation. No descriptor refresh or source substitution here.
    for (int pass = 0; pass < 2; pass++) {
        MTHandle *decodeHandle = mt_create(&descriptor, &limits, V2Authorize, NULL, &status);
        if (!decodeHandle) return 1;
        V2BindTransfer(decodeHandle);
        MDProbeLimits decodeLimits = {pass == 0 ? 0 : 30, 48000ull*900, 60000};
        MDProbeReport report = {0};
        before = Now();
        int error = md_compare_native_to_file(decodeHandle, destination.fileSystemRepresentation, &decodeLimits, &report);
        V2UnbindTransfer(decodeHandle); mt_destroy(decodeHandle);
        getrusage(RUSAGE_SELF, &usage);
        Output(JSONString(@{@"gate":pass == 0 ? @"native_decode_full" : @"native_decode_seek_30s",
            @"outcome":error == 0 ? @"pass" : @"fail", @"error":@(error),
            @"transport_category":@(mt_status_name(report.transport.status)), @"http_status":@(report.transport.http_status),
            @"local_error":@(report.local.ffmpeg_error), @"native_error":@(report.native.ffmpeg_error),
            @"equal_pcm":@(report.equal_pcm), @"local_frames":@(report.local.output_frames),
            @"native_frames":@(report.native.output_frames), @"nonzero_samples":@(report.native.nonzero_samples),
            @"rms":@(report.native.rms), @"pcm_sha256":@(report.native.pcm_sha256),
            @"first_output_seconds":@(report.native.first_output_seconds),
            @"source_sample_rate":@(report.native.source_sample_rate), @"source_channels":@(report.native.source_channels),
            @"network_bytes":@(report.transport.network_bytes), @"requests":@(report.transport.requests),
            @"buffer_high_bytes":@(report.transport.buffer_high_bytes), @"process_maxrss_bytes":@(usage.ru_maxrss),
            @"elapsed_ms":@((Now()-before)*1000)}));
        if (error != 0) return 1;
    }
#endif
    return 0;
}

int P0V2RunSource(NSString *bundle, BOOL next) {
    if (!P0V2BeginOperation(45)) return 75;
    @autoreleasepool {
        V2Client = @"TV_SAMSUNG"; V2Codec = @"aac";
        V2Descriptor = nil; V2CompletedPath = nil;
        extern int RunProof(NSString *, NSString *);
        int status = RunProof(bundle, next ? @"resolve_next" : @"resolve_first");
        if (status == 0 && !V2Descriptor) status = 1;
        if (status == 0) status = V2Transfer();
        if (V2ShouldStop()) status = 130;
        Output(JSONString(@{@"gate":@"source_operation", @"outcome":status == 0 ? @"pass" : @"fail",
            @"code":@(status), @"reason":V2StopReason(), @"observed_peak_rss_bytes":@(V2ObservedPeakRSS()),
            @"deadline_seconds":@45, @"next":@(next)}));
        NSString *path = status == 0 ? V2CompletedPath : nil;
        V2Descriptor = nil; V2CompletedPath = nil;
        P0V2EndOperation();
        if (path && mediaHandler) mediaHandler(path, next);
        return status;
    }
}

#ifndef P0_IOS
int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc < 3 || argc > 5) return 64;
        NSString *mode = @(argv[2]);
        if (![@[@"capabilities", @"resolve_first", @"resolve_next", @"direct_first", @"direct_next"] containsObject:mode]) return 64;
        if (argc > 3) V2Client = @(argv[3]);
        if (argc > 4) V2Codec = @(argv[4]);
        if (![@[@"IOS", @"VISIONOS", @"TV", @"TV_SAMSUNG", @"WEB", @"WEB_EMBEDDED"] containsObject:V2Client] ||
            ![@[@"aac", @"opus"] containsObject:V2Codec]) return 64;
        extern int RunProof(NSString *, NSString *);
        if (!P0V2BeginOperation(180)) return 75;
        int status = RunProof(@(argv[1]), mode);
        // Metadata/parser runtime is disposed before native media transfer.
        if (status == 0 && ![mode isEqual:@"capabilities"] && !V2Descriptor) status = 1;
        if (status == 0 && V2Descriptor) status = V2Transfer();
        if (V2ShouldStop()) status = 130;
        Output(JSONString(@{@"gate":@"source_operation", @"outcome":status == 0 ? @"pass" : @"fail",
            @"code":@(status), @"reason":V2StopReason(), @"observed_peak_rss_bytes":@(V2ObservedPeakRSS())}));
        V2Descriptor = nil; V2CompletedPath = nil;
        P0V2EndOperation();
        return status;
    }
}
#endif

int RunProof(NSString *bundlePath, NSString *mode) {
    @autoreleasepool {
        finished=NO; resultCode=1; peakAllocated=0;activeMode=mode; bridge=[[Bridge alloc] init]; runtime=JS_NewRuntime2(&Allocator,NULL);if(!runtime){[bridge.session invalidateAndCancel];bridge=nil;return 1;}
        NSUInteger heapMiB=64;
        JS_SetMemoryLimit(runtime,heapMiB*1024*1024); JS_SetMaxStackSize(runtime,1024*1024);
        double runtimeSeconds=[mode isEqual:@"interrupt"]?2:90;deadline=Now()+runtimeSeconds; JS_SetInterruptHandler(runtime,Interrupt,NULL); context=JS_NewContext(runtime);if(!context){JS_FreeRuntime(runtime);runtime=NULL;[bridge.session invalidateAndCancel];bridge=nil;return 1;}
        Register("nativePrint",NativePrint,1);Register("nativeFinish",NativeFinish,1);Register("nativeRequest",NativeRequest,1);Register("nativeCancel",NativeCancel,1);Register("nativeTimer",NativeTimer,2);Register("nativeURL",NativeURL,4);Register("nativeEncode",NativeEncode,1);Register("nativeDecode",NativeDecode,1);Register("nativeBase64",NativeBase64,2);Register("nativeSHA1",NativeSHA1,1);Register("nativeUUID",NativeUUID,0);Register("nativeEval",NativeEval,1);Register("nativeDescriptor",V2ReceiveDescriptor,1);
        JSValue global=JS_GetGlobalObject(context);JS_SetPropertyStr(context,global,"PROBE_MODE",JSString(context,mode));JS_SetPropertyStr(context,global,"SOURCE_CLIENT",JSString(context,V2Client));JS_SetPropertyStr(context,global,"SOURCE_CODEC",JSString(context,V2Codec));JS_FreeValue(context,global);
        NSData *source=[NSData dataWithContentsOfFile:bundlePath];
        JSValue result=JS_Eval(context,source.bytes,source.length,"p0.bundle.js",JS_EVAL_TYPE_GLOBAL);
        if(JS_IsException(result)){Error("bundle_load");finished=YES;}JS_FreeValue(context,result);
        while(!finished && Now()<deadline && !V2ShouldStop()) {
            @autoreleasepool {
                NSArray *events;
                @synchronized(bridge){events=[bridge.events copy];[bridge.events removeAllObjects];}
                for(NSDictionary *originalEvent in events) {
                    if(finished)break;if(V2ShouldStop()){finished=YES;resultCode=1;break;} NSDictionary *event=V2FilterEvent(originalEvent);if(!event){finished=YES;resultCode=1;break;}
                    JSValue g=JS_GetGlobalObject(context), cb=JS_GetPropertyStr(context,g,"nativeDeliver");NSData *data=event[@"body"];
                    JSValue args[]={JS_NewInt64(context,[event[@"id"] longLongValue]),JSString(context,JSONString(event[@"meta"])),JS_NewArrayBufferCopy(context,data.bytes,data.length)};
                    JSValue val=JS_Call(context,cb,g,3,args);if(JS_IsException(val)){Error("delivery");finished=YES;}
                    JS_FreeValue(context,val); for(int i=0;i<3;i++)JS_FreeValue(context,args[i]);JS_FreeValue(context,cb);JS_FreeValue(context,g);
                }
                for(NSDictionary *timer in [bridge.timers.allValues copy]) if(!finished && !V2ShouldStop() && [timer[@"due"] doubleValue]<=Now()) {
                    [bridge.timers removeObjectForKey:timer[@"id"]];JSValue g=JS_GetGlobalObject(context),cb=JS_GetPropertyStr(context,g,"nativeTimerDeliver"),arg=JS_NewInt64(context,[timer[@"id"] longLongValue]);
                    JSValue val=JS_Call(context,cb,g,1,&arg);if(JS_IsException(val)){Error("timer");finished=YES;}JS_FreeValue(context,val);JS_FreeValue(context,arg);JS_FreeValue(context,cb);JS_FreeValue(context,g);
                }
                JSContext *jobContext; int jobs=0, executedJobs=0;
                while(!finished && !V2ShouldStop() && executedJobs++<128 && (jobs=JS_ExecutePendingJob(runtime,&jobContext))>0){}
                if(jobs<0){Error("pending_job");finished=YES;}
                if(!finished) [NSThread sleepForTimeInterval:0.002];
            }
        }
        [bridge.session invalidateAndCancel];
        JSMemoryUsage memory;JS_ComputeMemoryUsage(runtime,&memory);struct rusage ru;getrusage(RUSAGE_SELF,&ru);
        Output(JSONString(@{@"gate":@"host_summary",@"outcome":finished?@"completed":@"timeout",@"requests":@(bridge.requestCount),@"received_bytes":@(bridge.receivedBytes),@"peak_concurrent":@(bridge.peakConcurrent),@"first_byte_samples":@(bridge.firstByteCount),@"js_memory_bytes":@(memory.memory_used_size),@"js_peak_allocated_bytes":@(peakAllocated),@"process_maxrss_bytes":@(ru.ru_maxrss),@"js_memory_limit_bytes":@(heapMiB*1024*1024),@"deadline_seconds":@(runtimeSeconds)}));
        JS_FreeContext(context);JS_FreeRuntime(runtime); context=NULL;runtime=NULL;bridge=nil;
        return resultCode;
    }
}

