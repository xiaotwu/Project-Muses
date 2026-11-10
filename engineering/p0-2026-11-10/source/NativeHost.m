// MIT. Independent P0 feasibility harness; not production code.
#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <mach/mach_time.h>
#import <sys/resource.h>
#include "quickjs.h"
#include <time.h>

static double Now(void) { return NSProcessInfo.processInfo.systemUptime; }
static JSRuntime *runtime;
static JSContext *context;
static double deadline;
static BOOL finished;
static int resultCode;
static uint64_t maxBody = 16 * 1024 * 1024;
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
    return [url.scheme isEqual:@"https"] && ([h isEqual:@"youtube.com"] || [h hasSuffix:@".youtube.com"] || [h isEqual:@"googlevideo.com"] || [h hasSuffix:@".googlevideo.com"]);
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
        if (body.length + data.length > maxBody) { entry[@"reason"] = @"response_limit"; [task cancel]; return; }
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
static int Interrupt(JSRuntime *rt, void *opaque) { return Now() > deadline; }
static int ScriptInterrupt(JSRuntime *rt,void *opaque) {return Now()>*(double *)opaque;}
NSString *P0IsolatedEvaluate(NSString *input) {
    NSString *source=[NSString stringWithFormat:@"(function(){%@})()",input];
    JSRuntime *isolated=JS_NewRuntime();JS_SetMemoryLimit(isolated,8*1024*1024);JS_SetMaxStackSize(isolated,512*1024);
    double stop=Now()+1;JS_SetInterruptHandler(isolated,ScriptInterrupt,&stop);JSContext *inner=JS_NewContext(isolated);
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
        if (bridge.requests.count>=4) return JS_ThrowRangeError(ctx,"native concurrency limit");
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
    if (ms<0) [bridge.timers removeObjectForKey:@(n)]; else bridge.timers[@(n)]=@{@"id":@(n),@"due":@(Now()+MIN(ms,60000)/1000)}; return JS_UNDEFINED;
}
static void Register(const char *name, JSCFunction *fn, int length) { JSValue g=JS_GetGlobalObject(context); JS_SetPropertyStr(context,g,name,JS_NewCFunction(context,fn,name,length)); JS_FreeValue(context,g); }
static void Error(const char *stage) {
    JSValue ex=JS_GetException(context), name=JS_GetPropertyStr(context,ex,"name"), message=JS_GetPropertyStr(context,ex,"message");
    NSString *msg=String(context,message); // Never print provider payloads, URL, headers, or dynamic scripts.
    BOOL safe= bridge.requestCount == 0 || [msg containsString:@"is not defined"] || [msg containsString:@"not a function"] || [msg containsString:@"stack overflow"] || [msg containsString:@"out of memory"] || [msg isEqual:@"interrupted"];
    Output(JSONString(@{@"gate":@(stage),@"outcome":@"fail",@"error_name":String(context,name),@"detail":safe?msg:@"redacted"}));
    if (bridge.requestCount == 0) { JSValue stack=JS_GetPropertyStr(context,ex,"stack");puts(String(context,stack).UTF8String);JS_FreeValue(context,stack); }
    JS_FreeValue(context,name);JS_FreeValue(context,message);JS_FreeValue(context,ex);
}
int RunProof(NSString *bundlePath, NSString *mode) {
    @autoreleasepool {
        finished=NO; resultCode=1; peakAllocated=0;activeMode=mode; bridge=[[Bridge alloc] init]; runtime=JS_NewRuntime2(&Allocator,NULL);
        NSUInteger heapMiB=[NSProcessInfo.processInfo.environment[@"P0_HEAP_MIB"] integerValue]==128 ? 128 : 64;
        JS_SetMemoryLimit(runtime,heapMiB*1024*1024); JS_SetMaxStackSize(runtime,1024*1024);
        double runtimeSeconds=[mode isEqual:@"interrupt"]?2:90;deadline=Now()+runtimeSeconds; JS_SetInterruptHandler(runtime,Interrupt,NULL); context=JS_NewContext(runtime);
        Register("nativePrint",NativePrint,1);Register("nativeFinish",NativeFinish,1);Register("nativeRequest",NativeRequest,1);Register("nativeCancel",NativeCancel,1);Register("nativeTimer",NativeTimer,2);Register("nativeURL",NativeURL,4);Register("nativeEncode",NativeEncode,1);Register("nativeDecode",NativeDecode,1);Register("nativeBase64",NativeBase64,2);Register("nativeSHA1",NativeSHA1,1);Register("nativeUUID",NativeUUID,0);Register("nativeEval",NativeEval,1);Register("nativeStoreMedia",NativeStoreMedia,3);
        JSValue global=JS_GetGlobalObject(context);JS_SetPropertyStr(context,global,"PROBE_MODE",JSString(context,mode));JS_FreeValue(context,global);
        NSData *source=[NSData dataWithContentsOfFile:bundlePath];
        JSValue result=JS_Eval(context,source.bytes,source.length,"p0.bundle.js",JS_EVAL_TYPE_GLOBAL);
        if(JS_IsException(result)){Error("bundle_load");finished=YES;}JS_FreeValue(context,result);
        while(!finished && Now()<deadline) {
            @autoreleasepool {
                NSArray *events;
                @synchronized(bridge){events=[bridge.events copy];[bridge.events removeAllObjects];}
                for(NSDictionary *event in events) {
                    JSValue g=JS_GetGlobalObject(context), cb=JS_GetPropertyStr(context,g,"nativeDeliver");NSData *data=event[@"body"];
                    JSValue args[]={JS_NewInt64(context,[event[@"id"] longLongValue]),JSString(context,JSONString(event[@"meta"])),JS_NewArrayBufferCopy(context,data.bytes,data.length)};
                    JSValue val=JS_Call(context,cb,g,3,args);if(JS_IsException(val)){Error("delivery");finished=YES;}
                    JS_FreeValue(context,val); for(int i=0;i<3;i++)JS_FreeValue(context,args[i]);JS_FreeValue(context,cb);JS_FreeValue(context,g);
                }
                for(NSDictionary *timer in [bridge.timers.allValues copy]) if([timer[@"due"] doubleValue]<=Now()) {
                    [bridge.timers removeObjectForKey:timer[@"id"]];JSValue g=JS_GetGlobalObject(context),cb=JS_GetPropertyStr(context,g,"nativeTimerDeliver"),arg=JS_NewInt64(context,[timer[@"id"] longLongValue]);
                    JSValue val=JS_Call(context,cb,g,1,&arg);if(JS_IsException(val)){Error("timer");finished=YES;}JS_FreeValue(context,val);JS_FreeValue(context,arg);JS_FreeValue(context,cb);JS_FreeValue(context,g);
                }
                JSContext *jobContext; int jobs;
                while((jobs=JS_ExecutePendingJob(runtime,&jobContext))>0){}
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
#ifndef P0_IOS
int main(int argc,char **argv){ if(argc<2)return 64;return RunProof(@(argv[1]),argc>2?@(argv[2]):@"catalog"); }
#endif
