// SPDX-License-Identifier: MIT
#include "../NativeControl.inc"
#include <stdio.h>
#include <sys/resource.h>
static atomic_uint cancelled;
void mt_cancel(MTHandle *handle) { (void)handle;atomic_fetch_add(&cancelled,1); }
int main(void) {
    struct rlimit core={0,0};if(setrlimit(RLIMIT_CORE,&core))return 1;
    @autoreleasepool {
        char handle;
        if(!P0V2BeginOperation(.03))return 2;
        V2BindTransfer(&handle);
        // Simulates a worker blocked outside JS; production monitor stays live.
        struct timespec interval={0,200000000};nanosleep(&interval,NULL);
        bool good=atomic_load(&cancelled)==1&&[V2StopReason() isEqual:@"deadline"]&&V2ObservedPeakRSS()>0&&V2ShouldStop();
        V2UnbindTransfer(&handle);P0V2EndOperation();
        if(!P0V2BeginOperation(1))return 3;
        good=good&&!V2ShouldStop()&&[V2StopReason() isEqual:@"none"];P0V2EndOperation();
        printf("{\"outcome\":\"%s\",\"real_clock_and_mach_rss\":true,\"network_requests\":0}\n",good?"pass":"fail");
        return good?0:4;
    }
}
