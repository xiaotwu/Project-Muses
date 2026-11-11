// MIT. Uses only the task-owned loopback fixture server.
#import <Foundation/Foundation.h>
#include <stdatomic.h>
#include <unistd.h>
#include "muses_transport.h"

static void require(BOOL ok,const char *message){if(!ok){fprintf(stderr,"FAIL %s\n",message);exit(1);}}
static int localPolicy(const char *url,void *context){return strncmp(url,"http://127.0.0.1:",17)==0;}
static MTLimits defaults(void){return(MTLimits){16ull<<20,16ull<<20,65536,512,1000,1,128ull<<20};}
static MTHandle *reader(NSString *url,MTLimits limits){MTDescriptor d={1,MT_DIRECT,url.UTF8String,NULL,0,0,0};MTStatus status;MTHandle*h=mt_create(&d,&limits,localPolicy,NULL,&status);require(h&&status==MT_OK,"create");return h;}
static void output(const char *name,MTHandle*h){MTStats s;mt_snapshot(h,&s);printf("{\"case\":\"%s\",\"status\":\"%s\",\"retry\":%d,\"total\":%llu,\"network\":%llu,\"unique\":%llu,\"delivered\":%llu,\"requests\":%u,\"buffer_high\":%llu,\"rss_high\":%llu,\"complete\":%d,\"sha256\":\"%s\"}\n",name,mt_status_name(s.status),s.retry,s.total_bytes,s.network_bytes,s.unique_validated_bytes,s.delivered_bytes,s.requests,s.buffer_high_bytes,s.resident_high_bytes,s.complete_file,s.sha256);}
static void backpressure(const MTStats *s,void*context){MTHandle*h=context;MTStats before,after;mt_snapshot(h,&before);uint8_t byte;size_t count;require(mt_read_at(h,0,&byte,1,&count)==MT_BUSY,"copy ownership reentry");usleep(150000);mt_snapshot(h,&after);require(before.requests==after.requests&&before.network_bytes==after.network_bytes,"backpressure failed");}

int main(int argc,char**argv){@autoreleasepool{
    require(argc==3,"base URL and owned output directory required");
    NSString*base=[NSString stringWithUTF8String:argv[1]],*directory=[NSString stringWithUTF8String:argv[2]];
    MTLimits limits=defaults();uint8_t bytes[65536];size_t got=0;MTStats s;
    MTHandle*h=reader([base stringByAppendingString:@"/range"],limits);
    require(mt_read_at(h,1000,bytes,1000,&got)==MT_OK&&got==1000,"first range");
    for(size_t i=0;i<got;i++)require(bytes[i]==(uint8_t)((1000+i)*31+7),"range byte identity");
    require(mt_read_at(h,1000,bytes,1000,&got)==MT_OK,"cached range");mt_snapshot(h,&s);require(s.requests==1&&s.unique_validated_bytes==65536,"duplicate progress");
    require(mt_read_at(h,0,bytes,sizeof(bytes),&got)==MT_OK,"backward seek");mt_snapshot(h,&s);require(s.unique_validated_bytes==66536,"overlap union");output("read_seek_cached",h);mt_destroy(h);

    h=reader([base stringByAppendingString:@"/range"],limits);
    NSString*file=[directory stringByAppendingPathComponent:@"complete.bin"];
    require(mt_copy_to_file(h,file.fileSystemRepresentation,backpressure,h)==MT_OK,"complete copy");mt_snapshot(h,&s);
    require(s.complete_file&&s.total_bytes==262144&&s.unique_validated_bytes==262144&&s.requests==4,"complete stats");
    require(s.buffer_high_bytes<=65536&&s.resident_high_bytes<=128ull*1024*1024,"resource caps");output("complete_backpressure",h);mt_destroy(h);

    NSArray*paths=@[@"/ignore",@"/forbidden",@"/wrong-range",@"/short",@"/changed",@"/oversize"];
    MTStatus expected[]={MT_RANGE_UNSUPPORTED,MT_HTTP_FORBIDDEN,MT_RANGE_INVALID,MT_NETWORK_ERROR,MT_CONTENT_CHANGED,MT_RESOURCE_LIMIT};
    for(NSUInteger i=0;i<paths.count;i++){
        h=reader([base stringByAppendingString:paths[i]],limits);
        MTStatus result=mt_read_at(h,0,bytes,sizeof(bytes),&got);
        if(i==4){require(result==MT_OK,"changed initial");result=mt_read_at(h,65536,bytes,sizeof(bytes),&got);}
        require(result==expected[i]||(i==3&&result==MT_TRUNCATED),"typed failure classification");
        output([paths[i] UTF8String]+1,h);mt_destroy(h);
    }
    h=reader([base stringByAppendingString:@"/late-forbidden"],limits);
    NSString*partial=[directory stringByAppendingPathComponent:@"must-not-complete.bin"];
    require(mt_copy_to_file(h,partial.fileSystemRepresentation,NULL,NULL)==MT_HTTP_FORBIDDEN,"late403");
    require(![[NSFileManager defaultManager]fileExistsAtPath:partial]&&[[NSFileManager defaultManager]fileExistsAtPath:[partial stringByAppendingString:@".partial"]],"partial committed");output("late403_partial",h);mt_destroy(h);

    h=reader([base stringByAppendingString:@"/slow"],limits);
    dispatch_semaphore_t ended=dispatch_semaphore_create(0);__block MTStatus cancelResult=MT_OK;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{uint8_t chunk[4096];size_t count;cancelResult=mt_read_at(h,0,chunk,sizeof(chunk),&count);dispatch_semaphore_signal(ended);});
    usleep(100000);double begin=NSProcessInfo.processInfo.systemUptime;mt_cancel(h);
    require(dispatch_semaphore_wait(ended,dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC))==0&&cancelResult==MT_CANCELLED,"cancel");
    printf("{\"case\":\"cancel_latency\",\"ms\":%.3f}\n",(NSProcessInfo.processInfo.systemUptime-begin)*1000);output("cancel",h);mt_destroy(h);

    limits.network_limit_bytes=70000;h=reader([base stringByAppendingString:@"/range"],limits);
    require(mt_read_at(h,0,bytes,sizeof(bytes),&got)==MT_OK,"budget first");require(mt_read_at(h,65536,bytes,sizeof(bytes),&got)==MT_OK&&got==4464,"budget remainder");require(mt_read_at(h,70000,bytes,sizeof(bytes),&got)==MT_RESOURCE_LIMIT,"network budget");output("network_cap",h);mt_destroy(h);
    limits=defaults();limits.maximum_requests=1;h=reader([base stringByAppendingString:@"/range"],limits);
    require(mt_read_at(h,0,bytes,sizeof(bytes),&got)==MT_OK,"request first");require(mt_read_at(h,65536,bytes,sizeof(bytes),&got)==MT_RESOURCE_LIMIT,"request budget");output("request_cap",h);mt_destroy(h);
    MTDescriptor expired={1,MT_DIRECT,[[base stringByAppendingString:@"/range"]UTF8String],NULL,0,0,1};MTStatus status;
    h=mt_create(&expired,&limits,localPolicy,NULL,&status);require(h!=NULL,"expiry create");require(mt_read_at(h,0,bytes,sizeof(bytes),&got)==MT_URL_EXPIRED,"expiry");mt_snapshot(h,&s);require(s.requests==0&&s.retry==MT_RETRY_FRESH_DESCRIPTOR,"expiry retries");output("known_expiry",h);mt_destroy(h);
    for(int kind=MT_HLS;kind<=MT_SABR;kind++){MTDescriptor descriptor={1,kind,"https://example.invalid/opaque",NULL,0,0,0};h=mt_create(&descriptor,&limits,localPolicy,NULL,&status);require(!h&&status==MT_KIND_UNSUPPORTED,"unsupported kind");}
    MTDescriptor mismatched={1,MT_DIRECT,[[base stringByAppendingString:@"/range"]UTF8String],NULL,0,123,0};limits=defaults();h=mt_create(&mismatched,&limits,localPolicy,NULL,&status);require(h!=NULL,"expected length create");require(mt_read_at(h,0,bytes,sizeof(bytes),&got)==MT_CONTENT_CHANGED,"expected length mismatch");output("declared_length_mismatch",h);mt_destroy(h);
    MTHeader publicHeaders[]={{"accept","*/*"},{"origin","https://www.youtube.com"},{"referer","https://www.youtube.com/"},{"DNT","?1"}};
    MTDescriptor publicDescriptor={1,MT_DIRECT,[[base stringByAppendingString:@"/header-check"]UTF8String],publicHeaders,4,0,0};h=mt_create(&publicDescriptor,&limits,localPolicy,NULL,&status);require(h!=NULL,"public headers create");require(mt_read_at(h,0,bytes,sizeof(bytes),&got)==MT_OK,"public header preservation");output("public_headers",h);mt_destroy(h);
    printf("{\"case\":\"capability_boundary\",\"hls\":\"unsupported\",\"sabr\":\"unsupported\"}\n");
    return 0;
}}
