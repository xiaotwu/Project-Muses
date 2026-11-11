#define P0_IOS
#include "/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-streaming/v2/kit/NativeHost.snapshot.m"
// MIT. Appended to an exact copied generated host. Its old complete-file API is
// never called. P0_IOS excludes the old desktop main and decoder diagnostic.
#include "stream_source.h"
#include <string.h>
void sp_cancel_resolver(void) { P0V2Cancel(); }
static MTLimits SPLimits(int loopback) { return (MTLimits){16*1024*1024,16*1024*1024,256*1024,512,5000,loopback,256*1024*1024}; }
static int SPLocalAllowed(const char *text,void *ignored) {
    NSURL *url=[NSURL URLWithString:@(text)];
    return [url.scheme isEqual:@"http"] && [url.host isEqual:@"127.0.0.1"];
}
SPSource sp_local_window(const char *url,uint64_t length,uint32_t window) {
    @autoreleasepool {
        SPSource result={0};result.total_bytes=length;result.descriptor_ns=sp_now_ns();
        MTDescriptor descriptor={1,MT_DIRECT,url,NULL,0,length,0};MTLimits limits=SPLimits(1);limits.block_bytes=window;MTStatus status;
        result.handle=mt_create(&descriptor,&limits,SPLocalAllowed,NULL,&status);result.error=status;return result;
    }
}
SPSource sp_local(const char *url,uint64_t length) { return sp_local_window(url,length,256*1024); }
SPSource sp_resolve(const char *bundle,int next,const char *codec) {
    SPSource result={0};
    if(!bundle || !codec || (strcmp(codec,"aac") && strcmp(codec,"opus"))) { result.error=64;return result; }
    if(!P0V2BeginOperation(45)) { result.error=75;return result; }
    @autoreleasepool {
        V2Client=@"TV_SAMSUNG";V2Codec=@(codec);V2Descriptor=nil;V2CompletedPath=nil;
        int status=RunProof(@(bundle),next?@"resolve_next":@"resolve_first");
        // RunProof has already destroyed its JS context/runtime here.
        NSDictionary *value=V2Descriptor;
        if(!status && !value)status=1;
        result.descriptor_ns=sp_now_ns();
        NSDictionary *availability=value[@"availability"];
        if(!status && (![availability isKindOfClass:NSDictionary.class] || ![availability[@"state"] isEqual:@"known"] ||
            ![availability[@"availableAtUnixMs"] isKindOfClass:NSNumber.class] || !isfinite([availability[@"availableAtUnixMs"] doubleValue])))status=2;
        double delay=status?0:MAX(0,[availability[@"availableAtUnixMs"] doubleValue]/1000.0-NSDate.date.timeIntervalSince1970);
        if(delay>20)status=2;
        double ready=Now()+delay;
        while(!status && Now()<ready) { if(V2ShouldStop()){status=130;break;}[NSThread sleepForTimeInterval:MIN(.02,ready-Now())]; }
        NSDictionary *headers=value[@"headers"];MTHeader list[8];uint32_t count=0;
        if(!status && (![headers isKindOfClass:NSDictionary.class] || headers.count>8))status=2;
        if(!status)for(NSString *key in headers) { if(![headers[key] isKindOfClass:NSString.class]){status=2;break;}list[count++]=(MTHeader){key.UTF8String,[headers[key] UTF8String]}; }
        if(V2ShouldStop())status=130;
        if(!status) {
            result.total_bytes=[value[@"content_length"] unsignedLongLongValue];
            MTDescriptor descriptor={1,MT_DIRECT,[value[@"url"] UTF8String],list,count,result.total_bytes,[value[@"expires_unix_seconds"] doubleValue]};
            MTLimits limits=SPLimits(0);MTStatus transport;
            // mt_create copies bounded native strings. It starts no request.
            result.handle=mt_create(&descriptor,&limits,V2Authorize,NULL,&transport);
            if(!result.handle)status=transport;
        }
        Output(JSONString(@{@"gate":@"stream_descriptor_handoff",@"outcome":status?@"fail":@"pass",@"next":@(next),@"codec":@(codec),@"total_bytes":@(result.total_bytes),@"code":@(status),@"media_bytes_in_js":@0}));
        V2Descriptor=nil;V2CompletedPath=nil;P0V2EndOperation();result.error=status;
    }
    return result;
}
