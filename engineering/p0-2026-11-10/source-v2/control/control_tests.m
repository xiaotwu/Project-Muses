// SPDX-License-Identifier: MIT
#import <Foundation/Foundation.h>
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <time.h>
#define P0_V2_CONTROL_TESTING 1
#include "../NativeControl.inc"

static _Atomic(uint64_t) fakeNow = 10000000000ull, fakeRSS = 104857600;
static atomic_bool rssAvailable = true;
static atomic_uint checks;
#define CHECK(x) do { atomic_fetch_add(&checks,1); if(!(x)){fprintf(stderr,"failed check line %d\n",__LINE__);abort();} } while(0)
static uint64_t P0V2TestNowNS(void) { return atomic_load(&fakeNow); }
static bool P0V2TestReadRSS(uint64_t *bytes) { *bytes=atomic_load(&fakeRSS);return atomic_load(&rssAvailable); }
typedef struct {
    pthread_mutex_t mutex; pthread_cond_t condition;
    bool alive, block, entered, exited; unsigned calls;
} Mock;
static Mock mock(void) { return (Mock){PTHREAD_MUTEX_INITIALIZER,PTHREAD_COND_INITIALIZER,true,false,false,false,0}; }
void mt_cancel(MTHandle *handle) {
    Mock *m=handle;pthread_mutex_lock(&m->mutex);CHECK(m->alive);
    m->calls++;m->entered=true;pthread_cond_broadcast(&m->condition);
    while(m->block)pthread_cond_wait(&m->condition,&m->mutex);
    m->exited=true;pthread_cond_broadcast(&m->condition);pthread_mutex_unlock(&m->mutex);
}
static void wait_cancel(Mock *m) {
    pthread_mutex_lock(&m->mutex);
    struct timespec interval={2,0};
    while(!m->entered){int error=pthread_cond_timedwait_relative_np(&m->condition,&m->mutex,&interval);CHECK(!error);}
    pthread_mutex_unlock(&m->mutex);
}
static void dispose(Mock *m) {
    pthread_mutex_lock(&m->mutex);m->alive=false;pthread_mutex_unlock(&m->mutex);
    pthread_cond_destroy(&m->condition);pthread_mutex_destroy(&m->mutex);
}
static void reset_fake(void) { atomic_fetch_add(&fakeNow,10000000000ull);atomic_store(&fakeRSS,104857600);atomic_store(&rssAvailable,true); }
static void *cancel_thread(void *ignored) { (void)ignored;P0V2Cancel();return NULL; }
static void *foreign_thread(void *ignored) {
    (void)ignored;CHECK(!P0V2BeginOperation(10));CHECK(V2ShouldStop());P0V2EndOperation();return NULL;
}
static atomic_bool unbindAttempt, unbindReturned;
static void *release_cancel(void *ptr) {
    Mock *m=ptr;
    while(!atomic_load(&unbindAttempt)){struct timespec t={0,1000000};nanosleep(&t,NULL);}
    pthread_mutex_lock(&m->mutex);CHECK(m->entered&&!m->exited);CHECK(!atomic_load(&unbindReturned));
    m->block=false;pthread_cond_broadcast(&m->condition);pthread_mutex_unlock(&m->mutex);return NULL;
}
static void test_limits_busy(void) {
    CHECK(V2ShouldStop());
    CHECK(!P0V2BeginOperation(0));CHECK(!P0V2BeginOperation(-1));CHECK(!P0V2BeginOperation(NAN));
    CHECK(!P0V2BeginOperation(INFINITY));CHECK(!P0V2BeginOperation(180.001));CHECK(!P0V2BeginOperation(0.0000000001));
    CHECK(P0V2BeginOperation(180));CHECK(!V2ShouldStop());CHECK(V2ObservedPeakRSS()==104857600);
    CHECK([V2StopReason() isEqual:@"none"]);CHECK(!P0V2BeginOperation(5));
    pthread_t thread;CHECK(!pthread_create(&thread,NULL,foreign_thread,NULL));CHECK(!pthread_join(thread,NULL));
    CHECK(!V2ShouldStop());CHECK([V2StopReason() isEqual:@"none"]);P0V2EndOperation();CHECK(V2ShouldStop());
    P0V2EndOperation();P0V2Cancel();CHECK([V2StopReason() isEqual:@"none"]);
}
static void test_cancel_lifetime(void) {
    reset_fake();CHECK(P0V2BeginOperation(10));Mock m=mock();m.block=true;V2BindTransfer(&m);
    pthread_t cancel,release;CHECK(!pthread_create(&cancel,NULL,cancel_thread,NULL));wait_cancel(&m);
    CHECK([V2StopReason() isEqual:@"cancelled"]);CHECK(V2ShouldStop());
    atomic_store(&unbindAttempt,false);atomic_store(&unbindReturned,false);
    CHECK(!pthread_create(&release,NULL,release_cancel,&m));atomic_store(&unbindAttempt,true);
    V2UnbindTransfer(&m);atomic_store(&unbindReturned,true);CHECK(m.exited);
    CHECK(!pthread_join(cancel,NULL));CHECK(!pthread_join(release,NULL));CHECK(m.calls==1);
    P0V2Cancel();CHECK(m.calls==1);dispose(&m);P0V2Cancel();P0V2EndOperation();
    CHECK([V2StopReason() isEqual:@"cancelled"]);
    CHECK(P0V2BeginOperation(10));CHECK(!V2ShouldStop());CHECK([V2StopReason() isEqual:@"none"]);
    CHECK(V2ObservedPeakRSS()==104857600);P0V2EndOperation();
}
static void test_watchdog_deadline(void) {
    reset_fake();CHECK(P0V2BeginOperation(1));Mock m=mock();V2BindTransfer(&m);
    atomic_fetch_add(&fakeNow,1000000001ull);
    // No ShouldStop polling: the watcher must cancel the blocked mock itself.
    wait_cancel(&m);CHECK([V2StopReason() isEqual:@"deadline"]);CHECK(V2ShouldStop());
    P0V2Cancel();CHECK([V2StopReason() isEqual:@"deadline"]);CHECK(m.calls==1);
    V2UnbindTransfer(&m);dispose(&m);P0V2EndOperation();
}
static void test_watchdog_rss(void) {
    reset_fake();CHECK(P0V2BeginOperation(10));Mock m=mock();V2BindTransfer(&m);
    atomic_store(&fakeRSS,268435457);wait_cancel(&m);
    CHECK([V2StopReason() isEqual:@"rss_limit"]);CHECK(V2ObservedPeakRSS()==268435457);
    V2UnbindTransfer(&m);dispose(&m);P0V2EndOperation();
    reset_fake();CHECK(P0V2BeginOperation(10));Mock unavailable=mock();V2BindTransfer(&unavailable);
    atomic_store(&rssAvailable,false);wait_cancel(&unavailable);CHECK([V2StopReason() isEqual:@"rss_observer_unavailable"]);
    V2UnbindTransfer(&unavailable);dispose(&unavailable);P0V2EndOperation();
    reset_fake();atomic_store(&fakeRSS,268435456);CHECK(P0V2BeginOperation(10));CHECK(!V2ShouldStop());P0V2EndOperation();
}
static void test_bind_rules(void) {
    reset_fake();Mock idle=mock();V2BindTransfer(&idle);CHECK(idle.calls==1);dispose(&idle);
    CHECK(P0V2BeginOperation(10));Mock first=mock(),second=mock();V2BindTransfer(&first);V2BindTransfer(&first);
    CHECK(first.calls==0);V2BindTransfer(&second);CHECK(first.calls==1&&second.calls==1);
    CHECK([V2StopReason() isEqual:@"transfer_binding"]);V2UnbindTransfer(&second);V2UnbindTransfer(&first);
    dispose(&first);dispose(&second);P0V2EndOperation();
    CHECK(P0V2BeginOperation(10));P0V2Cancel();Mock late=mock();V2BindTransfer(&late);CHECK(late.calls==1);
    V2UnbindTransfer(&late);dispose(&late);P0V2EndOperation();
    CHECK(P0V2BeginOperation(10));Mock attached=mock();V2BindTransfer(&attached);P0V2EndOperation();
    CHECK(attached.calls==1);dispose(&attached);P0V2Cancel();
}
typedef struct { pthread_mutex_t mutex; pthread_cond_t condition; bool ready,finish; } Owner;
static void *new_owner(void *ptr) {
    Owner *o=ptr;CHECK(P0V2BeginOperation(10));pthread_mutex_lock(&o->mutex);o->ready=true;pthread_cond_signal(&o->condition);
    while(!o->finish)pthread_cond_wait(&o->condition,&o->mutex);pthread_mutex_unlock(&o->mutex);
    CHECK(!V2ShouldStop());P0V2EndOperation();return NULL;
}
static void test_generations(void) {
    reset_fake();CHECK(P0V2BeginOperation(10));P0V2EndOperation();
    Owner owner={PTHREAD_MUTEX_INITIALIZER,PTHREAD_COND_INITIALIZER,false,false};pthread_t worker;
    CHECK(!pthread_create(&worker,NULL,new_owner,&owner));pthread_mutex_lock(&owner.mutex);
    while(!owner.ready)pthread_cond_wait(&owner.condition,&owner.mutex);pthread_mutex_unlock(&owner.mutex);
    // The ended worker cannot end or bind into another worker's new operation.
    P0V2EndOperation();CHECK(V2ShouldStop());CHECK(!P0V2BeginOperation(10));
    Mock stale=mock();V2BindTransfer(&stale);CHECK(stale.calls==1);dispose(&stale);
    CHECK([V2StopReason() isEqual:@"none"]);
    pthread_mutex_lock(&owner.mutex);owner.finish=true;pthread_cond_signal(&owner.condition);pthread_mutex_unlock(&owner.mutex);
    CHECK(!pthread_join(worker,NULL));pthread_cond_destroy(&owner.condition);pthread_mutex_destroy(&owner.mutex);
    for(int i=0;i<20;i++){CHECK(P0V2BeginOperation(10));CHECK(!V2ShouldStop());P0V2EndOperation();}
}
int main(void) {
    struct rlimit core={0,0};CHECK(!setrlimit(RLIMIT_CORE,&core));
    @autoreleasepool {
        test_limits_busy();test_cancel_lifetime();test_watchdog_deadline();test_watchdog_rss();test_bind_rules();test_generations();
        printf("{\"outcome\":\"pass\",\"checks\":%u,\"network_requests\":0,\"core_dumps\":false}\n",atomic_load(&checks));
    }
    return 0;
}
