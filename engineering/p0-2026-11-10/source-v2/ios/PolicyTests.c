// MIT. Actual controller policy tests. No network, UI, or audio output.
#include "RunPolicy.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>

typedef struct { P0RunPolicy *policy; atomic_int *won; } Race;
static void *claim(void *data) {
    Race *r=data;if(p0_next(r->policy,130,true,true)==P0_NEXT_CLAIMED)atomic_fetch_add(r->won,1);return NULL;
}
static void *cancel(void *data) { Race *r=data;p0_cancel(r->policy,P0_STOP_USER);return NULL; }
int main(void) {
    P0RunPolicy p;p0_policy_init(&p);
    assert(p0_next(&p,100,true,true)==P0_NEXT_WAIT);
    atomic_store(&p.audio_started,100);
    assert(p0_next(&p,129.999999,true,true)==P0_NEXT_WAIT);
    assert(p0_next(&p,130,true,false)==P0_NEXT_NOT_BACKGROUND);
    assert(p0_next(&p,130,false,true)==P0_NEXT_NOT_BACKGROUND);
    assert(!atomic_load(&p.next_claimed));
    assert(p0_next(&p,130,true,true)==P0_NEXT_CLAIMED);
    assert(p0_next(&p,200,true,true)==P0_NEXT_ALREADY);
    assert(p0_cancel(&p,P0_STOP_USER));assert(!p0_cancel(&p,P0_STOP_DEADLINE));
    assert(atomic_load(&p.stop_reason)==P0_STOP_USER);
    assert(p0_next(&p,200,true,true)==P0_NEXT_CANCELLED);
    P0RunPolicy replacement;p0_policy_init(&replacement);
    assert(!p0_cancelled(&replacement));assert(p0_cancelled(&p));
    for(int attempt=0;attempt<100;attempt++) {
        P0RunPolicy run;p0_policy_init(&run);atomic_store(&run.audio_started,100);
        atomic_int won;atomic_init(&won,0);Race r={&run,&won};pthread_t threads[16];
        for(int i=0;i<16;i++)assert(!pthread_create(&threads[i],NULL,claim,&r));
        for(int i=0;i<16;i++)assert(!pthread_join(threads[i],NULL));
        assert(atomic_load(&won)==1);
        for(int i=0;i<16;i++)assert(!pthread_create(&threads[i],NULL,cancel,&r));
        for(int i=0;i<16;i++)assert(!pthread_join(threads[i],NULL));
        assert(p0_cancelled(&run));assert(p0_next(&run,130,true,true)==P0_NEXT_CANCELLED);
    }
    const uint64_t m=1024*1024;
    assert(p0_storage_admit(30*m,34*m,64*m));
    assert(!p0_storage_admit(30*m+1,34*m,64*m));
    assert(!p0_storage_admit(UINT64_MAX,34*m,64*m));
    assert(!p0_storage_admit(0,UINT64_MAX,64*m));
    assert(p0_trace_admit(503,503*4096,4096,false));
    assert(!p0_trace_admit(504,504*4096,4096,false));
    assert(p0_trace_admit(511,511*4096,4096,true));
    assert(!p0_trace_admit(512,512*4096,1,true));
    assert(!p0_trace_admit(1,2*1024*1024,1,true));
    assert(!p0_trace_admit(0,0,4097,false));
    puts("{\"gate\":\"ios_controller_policy\",\"outcome\":\"pass\",\"concurrent_claim_rounds\":100,\"threads_per_round\":16,\"network\":false,\"audio\":false}");
    return 0;
}
