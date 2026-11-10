// SPDX-License-Identifier: MIT
// Exercise the exact generated host in one TU; do not copy its implementation.
#define main P0OriginalMain
#include "NativeHost.v2.m"
#undef main
#include <stdio.h>
#include <sys/resource.h>

static unsigned HostChecks;
#define VERIFY(x) do{HostChecks++;if(!(x)){fprintf(stderr,"host wiring check failed at %d\n",__LINE__);return false;}}while(0)
static void *HostCancel(void *opaque) { long ns=*(long *)opaque;struct timespec t={0,ns};nanosleep(&t,NULL);P0V2Cancel();return NULL; }
static bool Fresh(NSString *directory) {
    VERIFY(P0V2BeginOperation(1));int result=RunProof([directory stringByAppendingPathComponent:@"fresh.js"],@"fixture");
    bool good=result==0&&!V2ShouldStop()&&[V2StopReason() isEqual:@"none"];
    P0V2EndOperation();VERIFY(good);return true;
}
static bool Proof(NSString *directory,NSString *fixture,double timeout,bool cancel) {
    VERIFY(P0V2BeginOperation(timeout));pthread_t thread;long delay=30000000;
    if(cancel)VERIFY(!pthread_create(&thread,NULL,HostCancel,&delay));
    double started=Now();int result=RunProof([directory stringByAppendingPathComponent:fixture],@"fixture");
    if(cancel)VERIFY(!pthread_join(thread,NULL));
    double elapsed=Now()-started;NSString *reason=V2StopReason();bool stopped=V2ShouldStop();
    P0V2EndOperation();
    Output(JSONString(@{@"gate":@"host_wiring_case",@"fixture":fixture,@"result":@(result),@"elapsed_ms":@(elapsed*1000),@"reason":reason,@"stopped":@(stopped)}));
    if([fixture isEqual:@"timers.js"]){VERIFY(result==0&&!stopped&&[reason isEqual:@"none"]);}
    else {VERIFY(result!=0&&stopped);VERIFY([reason isEqual:cancel?@"cancelled":@"deadline"]);VERIFY(elapsed<.8);}
    return Fresh(directory);
}
static bool Parser(NSString *path,NSString *directory,bool during) {
    NSData *player=[NSData dataWithContentsOfFile:path];VERIFY(player.length==2658728);
    __block NSDictionary *observed=nil;
    P0SetLogHandler(^(NSString *line){NSDictionary *event=[NSJSONSerialization JSONObjectWithData:[line dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];if([event[@"gate"] isEqual:@"native_player_reduce"])observed=event;});
    VERIFY(P0V2BeginOperation(1));pthread_t thread;long delay=1000000;
    if(during)VERIFY(!pthread_create(&thread,NULL,HostCancel,&delay));else P0V2Cancel();
    double started=Now();NSDictionary *result=V2FilterEvent(@{@"meta":@{@"status":@200,@"url":@"https://www.youtube.com/s/player/public-fixture/base.js",@"headers":@{}},@"body":player});
    if(during)VERIFY(!pthread_join(thread,NULL));
    double elapsed=Now()-started;bool cancelled=V2ShouldStop();P0V2EndOperation();P0SetLogHandler(nil);
    VERIFY(result==nil&&cancelled);VERIFY([observed[@"category"] isEqual:@"cancelled"]);
    VERIFY([observed[@"native_live_after_bytes"] unsignedLongLongValue]==0);VERIFY(elapsed<.8);
    Output(JSONString(@{@"gate":@"host_wiring_parser",@"cancel_during_parse":@(during),@"elapsed_ms":@(elapsed*1000),@"live_bytes":observed[@"native_live_after_bytes"],@"outcome":@"pass"}));
    return Fresh(directory);
}
int main(int argc,char **argv) {
    struct rlimit core={0,0};if(setrlimit(RLIMIT_CORE,&core)||argc!=3)return 64;
    setvbuf(stdout,NULL,_IOLBF,0);
    @autoreleasepool {
        NSString *directory=@(argv[1]),*player=@(argv[2]);
        bool good=Proof(directory,@"promise-chain.js",.15,false)
          &&Proof(directory,@"timers.js",1,false)
          &&Proof(directory,@"isolated-loop.js",.15,false)
          &&Proof(directory,@"isolated-loop.js",1,true)
          &&Parser(player,directory,false)&&Parser(player,directory,true);
        struct rusage usage;getrusage(RUSAGE_SELF,&usage);
        Output(JSONString(@{@"gate":@"host_wiring_summary",@"outcome":good?@"pass":@"fail",@"checks":@(HostChecks),@"network_requests":@0,@"process_maxrss_bytes":@(usage.ru_maxrss)}));
        return good?0:1;
    }
}
