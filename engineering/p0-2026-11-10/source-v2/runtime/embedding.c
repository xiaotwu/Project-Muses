// SPDX-License-Identifier: MIT
// Embedding-only offline resource/lifetime probe; no runtime CLI dependency.
#include "quickjs.h"
#include <CommonCrypto/CommonDigest.h>
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

typedef union { struct { size_t size; } data; max_align_t alignment; } Header;
typedef struct {
    size_t live, peak, count, limit, denials;
    double deadline;
    atomic_bool cancelled;
    bool deadline_hit;
    size_t allocation_iterations;
} Stats;
typedef struct { JSRuntime *runtime; JSContext *context; Stats stats; } Engine;
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9; }
static void *allocate(void *opaque,size_t n) {
    Stats *s=opaque;
    if(n>SIZE_MAX-sizeof(Header)||s->live>s->limit||n+sizeof(Header)>s->limit-s->live){s->denials++;return NULL;}
    Header *h=malloc(n+sizeof(*h));if(!h){s->denials++;return NULL;}
    h->data.size=n;s->live+=n+sizeof(*h);s->count++;if(s->live>s->peak)s->peak=s->live;return h+1;
}
static void *allocate_zero(void *opaque,size_t count,size_t size) {
    if(size&&count>SIZE_MAX/size){((Stats *)opaque)->denials++;return NULL;}
    void *p=allocate(opaque,count*size);if(p)memset(p,0,count*size);return p;
}
static void release(void *opaque,void *p) {
    if(!p)return;Stats *s=opaque;Header *h=(Header *)p-1;
    assert(s->live>=h->data.size+sizeof(*h)&&s->count);s->live-=h->data.size+sizeof(*h);s->count--;free(h);
}
static void *resize(void *opaque,void *p,size_t n) {
    if(!p)return allocate(opaque,n);if(!n){release(opaque,p);return NULL;}
    Stats *s=opaque;Header *h=(Header *)p-1;size_t old=h->data.size;
    if(n>SIZE_MAX-sizeof(*h)||s->live<old||s->live-old>s->limit||n>s->limit-(s->live-old)){s->denials++;return NULL;}
    h=realloc(h,n+sizeof(*h));if(!h){s->denials++;return NULL;}
    h->data.size=n;s->live=s->live-old+n;if(s->live>s->peak)s->peak=s->live;return h+1;
}
static size_t usable(const void *p){return p?((const Header *)p)[-1].data.size:0;}
static const JSMallocFunctions allocator={allocate_zero,allocate,release,resize,usable};
static int interrupt(JSContext *context,void *opaque) {
    (void)context;Stats *s=opaque;
    if(atomic_load(&s->cancelled))return 1;
    if(now()>s->deadline){s->deadline_hit=true;return 1;}return 0;
}
static int create(Engine *e,size_t bytes,double seconds) {
    memset(e,0,sizeof(*e));e->stats.limit=bytes;e->stats.deadline=now()+seconds;atomic_init(&e->stats.cancelled,false);
    e->runtime=JS_NewRuntime2(&allocator,&e->stats);if(!e->runtime)return 0;
    JS_SetRuntimeOpaque(e->runtime,&e->stats);JS_SetMemoryLimit(e->runtime,bytes);
    JS_SetMaxStackSize(e->runtime,1024*1024);JS_SetInterruptHandler(e->runtime,interrupt,&e->stats);
    e->context=JS_NewContext(e->runtime);return e->context!=NULL;
}
static int destroy(Engine *e,const char *phase) {
    if(e->context)JS_FreeContext(e->context);if(e->runtime)JS_FreeRuntime(e->runtime);
    e->context=NULL;e->runtime=NULL;
    printf("{\"phase\":\"%s_teardown\",\"backing_live_bytes\":%zu,\"backing_live_allocations\":%zu,\"backing_peak_bytes\":%zu,\"allocator_denials\":%zu}\n",phase,e->stats.live,e->stats.count,e->stats.peak,e->stats.denials);
    return e->stats.live==0&&e->stats.count==0;
}
static JSValue mark(JSContext *c,JSValueConst self,int argc,JSValueConst *argv) {
    (void)self;const char *label=argc?JS_ToCString(c,argv[0]):NULL;Stats *s=JS_GetRuntimeOpaque(JS_GetRuntime(c));
    JSMemoryUsage u;JS_ComputeMemoryUsage(JS_GetRuntime(c),&u);struct rusage r;getrusage(RUSAGE_SELF,&r);
    printf("{\"phase\":\"%s\",\"logical_js_bytes\":%lld,\"backing_live_bytes\":%zu,\"backing_peak_bytes\":%zu,\"process_maxrss_bytes\":%ld}\n",label?label:"mark",(long long)u.malloc_size,s->live,s->peak,r.ru_maxrss);
    JS_FreeCString(c,label);fflush(stdout);return JS_UNDEFINED;
}
static JSValue collect(JSContext *c,JSValueConst self,int argc,JSValueConst *argv) {
    (void)self;(void)argc;(void)argv;JS_RunGC(JS_GetRuntime(c));return JS_UNDEFINED;
}
static bool discard_exception(Engine *e,const char *phase) {
    // Do not allocate strings, inspect properties, or construct a backtrace under OOM.
    JSValue error=JS_GetException(e->context);bool uncatchable=JS_IsUncatchableError(error);
    printf("{\"phase\":\"%s_exception\",\"uncatchable\":%s,\"error_object\":%s,\"null_exception\":%s,\"allocator_denials\":%zu,\"cancel_requested\":%s,\"deadline_hit\":%s}\n",phase,uncatchable?"true":"false",JS_IsError(error)?"true":"false",JS_IsNull(error)?"true":"false",e->stats.denials,atomic_load(&e->stats.cancelled)?"true":"false",e->stats.deadline_hit?"true":"false");
    JS_FreeValue(e->context,error);return uncatchable;
}
static char *read_file(const char *path,size_t *length) {
    FILE *f=fopen(path,"rb");if(!f)return NULL;
    if(fseek(f,0,SEEK_END)){fclose(f);return NULL;}long n=ftell(f);rewind(f);
    if(n<0||n>4*1024*1024){fclose(f);return NULL;}char *data=malloc((size_t)n+1);
    if(!data){fclose(f);return NULL;}*length=fread(data,1,(size_t)n,f);fclose(f);
    if(*length!=(size_t)n){free(data);return NULL;}data[n]=0;return data;
}
static void digest(const char *data,size_t n,char out[65]) {
    unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data,(CC_LONG)n,hash);
    for(size_t i=0;i<sizeof(hash);i++)sprintf(out+i*2,"%02x",hash[i]);
}
static int set(JSContext *c,JSValueConst global,const char *key,JSValue value) {
    if(JS_IsException(value))return 0;return JS_SetPropertyStr(c,global,key,value)>=0;
}
static int fresh_success(void) {
    Engine e;if(!create(&e,8*1024*1024,1)){destroy(&e,"fresh");return 0;}
    const char script[]="JSON.stringify({answer:6*7,promise:typeof Promise,buffer:new Uint8Array([1,2,3]).length})";
    JSValue v=JS_Eval(e.context,script,sizeof(script)-1,"fresh.js",JS_EVAL_TYPE_GLOBAL);
    int good=0;if(!JS_IsException(v)){const char *text=JS_ToCString(e.context,v);good=text&&!strcmp(text,"{\"answer\":42,\"promise\":\"function\",\"buffer\":3}");JS_FreeCString(e.context,text);}else discard_exception(&e,"fresh");
    JS_FreeValue(e.context,v);good=destroy(&e,"fresh")&&good;
    printf("{\"phase\":\"fresh_runtime\",\"outcome\":\"%s\"}\n",good?"pass":"fail");return good;
}
static int solver(const char *script,size_t length) {
    Engine e;if(!create(&e,8*1024*1024,1)){destroy(&e,"solver");return 0;}
    JS_SetMaxStackSize(e.runtime,512*1024);char *wrapper=malloc(length+32);
    if(!wrapper){destroy(&e,"solver");return 0;}memcpy(wrapper,"(function(){",12);memcpy(wrapper+12,script,length);memcpy(wrapper+12+length,"})()",5);
    JSValue v=JS_Eval(e.context,wrapper,length+16,"isolated-solver.js",JS_EVAL_TYPE_GLOBAL);free(wrapper);int good=0;
    if(JS_IsException(v))discard_exception(&e,"solver");
    else {
        JSValue n=JS_GetPropertyStr(e.context,v,"n"),s=JS_GetPropertyStr(e.context,v,"sig");size_t nn=0,sn=0;
        const char *nt=JS_IsString(n)?JS_ToCStringLen(e.context,&nn,n):NULL,*st=JS_IsString(s)?JS_ToCStringLen(e.context,&sn,s):NULL;
        good=nt&&st&&nn>0&&sn>0&&strncmp(nt,"enhanced_except_",16);
        char nh[65]={0},sh[65]={0};if(nt)digest(nt,nn,nh);if(st)digest(st,sn,sh);
        printf("{\"phase\":\"isolated_solver\",\"outcome\":\"%s\",\"n_length\":%zu,\"sig_length\":%zu,\"n_sha256\":\"%s\",\"sig_sha256\":\"%s\",\"heap_limit_bytes\":8388608}\n",good?"pass":"fail",nn,sn,nh,sh);
        JS_FreeCString(e.context,nt);JS_FreeCString(e.context,st);JS_FreeValue(e.context,n);JS_FreeValue(e.context,s);
    }
    JS_FreeValue(e.context,v);return destroy(&e,"solver")&&good;
}
static int extract(const char *bundle_path,const char *input_path,const char *reference_path,bool parse_only) {
    size_t bn=0,pn=0;char *bundle=read_file(bundle_path,&bn),*player=read_file(input_path,&pn);if(!bundle||!player){free(bundle);free(player);return 0;}
    Engine e;if(!create(&e,64*1024*1024,15)){free(bundle);free(player);destroy(&e,"extract");return 0;}
    JSContext *c=e.context;JSValue global=JS_GetGlobalObject(c);int good=0;char *test_copy=NULL;size_t test_length=0;
    bool configured=set(c,global,"nativeMark",JS_NewCFunction(c,mark,"nativeMark",1))
      &&set(c,global,"nativeGC",JS_NewCFunction(c,collect,"nativeGC",0))
      &&set(c,global,"playerSource",JS_NewStringLen(c,player,pn))
      &&set(c,global,"PROBE_PHASE",JS_NewString(c,parse_only?"parse_only":"extract"));free(player);
    JSValue value=configured?JS_Eval(c,bundle,bn,"extraction.js",JS_EVAL_TYPE_GLOBAL):JS_EXCEPTION;free(bundle);
    if(JS_IsException(value)) {
        discard_exception(&e,"extract");
        // The bounded allocator can deny creation of the error object itself.
        // An exception plus a recorded denial tests graceful failure, not the
        // stronger claim that every exhausted-heap exception is uncatchable.
        good=parse_only&&e.stats.denials>0&&!e.stats.deadline_hit&&!atomic_load(&e.stats.cancelled);
        printf("{\"phase\":\"extraction_result\",\"outcome\":\"%s\",\"classification\":\"%s\"}\n",good?"pass":"fail",good?"bounded_allocator_failure":"unexpected_exception");
    } else if(parse_only){good=1;printf("{\"phase\":\"extraction_result\",\"outcome\":\"pass\",\"classification\":\"full_parse_completed\"}\n");}
    else {
        JSValue output=JS_GetPropertyStr(c,global,"solverText"),test=JS_GetPropertyStr(c,global,"testText"),stamp=JS_GetPropertyStr(c,global,"signatureTimestamp");
        size_t length=0;const char *text=JS_ToCStringLen(c,&length,output),*test_text=JS_ToCStringLen(c,&test_length,test);int32_t timestamp=0;JS_ToInt32(c,&timestamp,stamp);
        size_t reference_n=0;char *reference=read_file(reference_path,&reference_n);bool matches=text&&reference&&length==reference_n&&!memcmp(text,reference,length);free(reference);
        if(text&&test_text&&length<=256*1024&&test_length<=512*1024&&timestamp>0&&matches){test_copy=malloc(test_length+1);if(test_copy){memcpy(test_copy,test_text,test_length+1);good=1;}}
        char hash[65]={0};if(text)digest(text,length,hash);
        printf("{\"phase\":\"solver_output\",\"outcome\":\"%s\",\"bytes\":%zu,\"sha256\":\"%s\",\"matches_reference\":%s,\"signature_timestamp\":%d}\n",good?"pass":"fail",length,hash,matches?"true":"false",timestamp);
        JS_FreeCString(c,text);JS_FreeCString(c,test_text);JS_FreeValue(c,output);JS_FreeValue(c,test);JS_FreeValue(c,stamp);
    }
    JS_FreeValue(c,value);JS_FreeValue(c,global);good=destroy(&e,"extract")&&good;
    if(test_copy){good=solver(test_copy,test_length)&&good;free(test_copy);}int fresh=fresh_success();return good&&fresh;
}
static void *cancel_later(void *opaque) { struct timespec delay={0,30*1000*1000};nanosleep(&delay,NULL);atomic_store(&((Stats *)opaque)->cancelled,true);return NULL; }
static JSValue allocation_completed(JSContext *c,JSValueConst self,int argc,JSValueConst *argv) {
    (void)self;(void)argc;(void)argv;Stats *s=JS_GetRuntimeOpaque(JS_GetRuntime(c));s->allocation_iterations++;return JS_UNDEFINED;
}
static int resource_test(bool cancel) {
    Engine e;if(!create(&e,8*1024*1024,1)){destroy(&e,"resource");return 0;}
    JSValue global=JS_GetGlobalObject(e.context);
    if(!set(e.context,global,"nativeAllocationCompleted",JS_NewCFunction(e.context,allocation_completed,"nativeAllocationCompleted",0))){JS_FreeValue(e.context,global);destroy(&e,"resource");return 0;}
    JS_FreeValue(e.context,global);
    const char *script=cancel?"try { for (;;) {} } catch(e) { globalThis.caught=true; }":"try { const a=[]; for(;;) { a.push(new Uint8Array(1048576)); nativeAllocationCompleted(); } } catch(e) { globalThis.caught=true; }";
    pthread_t thread;bool started=false;if(cancel){started=pthread_create(&thread,NULL,cancel_later,&e.stats)==0;if(!started){destroy(&e,"resource");return 0;}}
    JSValue value=JS_Eval(e.context,script,strlen(script),"resource.js",JS_EVAL_TYPE_GLOBAL);if(started)pthread_join(thread,NULL);
    int good=JS_IsException(value)&&discard_exception(&e,cancel?"cancel":"oom");
    // For this fixed workload NG's logical limit can reject the next 1 MiB
    // request before calling the backing allocator; its denial count stays 0.
    good=good&&(cancel?atomic_load(&e.stats.cancelled):e.stats.allocation_iterations>0)&&!e.stats.deadline_hit;
    JS_FreeValue(e.context,value);good=destroy(&e,"resource")&&good;
    printf("{\"phase\":\"%s\",\"outcome\":\"%s\",\"completed_1mib_allocations\":%zu}\n",cancel?"host_cancellation":"explicit_oom",good?"pass":"fail",e.stats.allocation_iterations);int fresh=fresh_success();return good&&fresh;
}
static int context_failure(void) {
    Engine e;memset(&e,0,sizeof(e));e.stats.limit=8*1024*1024;e.stats.deadline=now()+1;atomic_init(&e.stats.cancelled,false);
    e.runtime=JS_NewRuntime2(&allocator,&e.stats);if(!e.runtime){destroy(&e,"context");return 0;}
    JS_SetMemoryLimit(e.runtime,1);e.context=JS_NewContext(e.runtime);int good=e.context==NULL;
    printf("{\"phase\":\"context_oom\",\"outcome\":\"%s\",\"fault_injection_logical_limit\":1}\n",good?"pass":"fail");return destroy(&e,"context")&&good&&fresh_success();
}
static int smoke(const char *path) {
    size_t n=0;char *script=read_file(path,&n);if(!script)return 0;Engine e;
    if(!create(&e,64*1024*1024,2)){free(script);destroy(&e,"smoke");return 0;}
    JSValue value=JS_Eval(e.context,script,n,"offline-fetch-shim.js",JS_EVAL_TYPE_GLOBAL);free(script);int good=!JS_IsException(value);
    if(!good)discard_exception(&e,"smoke");JS_FreeValue(e.context,value);
    JSContext *pending=NULL;int jobs=0,rc=0;
    while(good&&JS_IsJobPending(e.runtime)&&jobs<128){rc=JS_ExecutePendingJob(e.runtime,&pending);jobs++;if(rc<0){good=0;discard_exception(&e,"smoke_job");}}
    JSValue global=JS_GetGlobalObject(e.context),done=JS_GetPropertyStr(e.context,global,"smokeDone");good=good&&JS_ToBool(e.context,done)==1&&!JS_IsJobPending(e.runtime);
    printf("{\"phase\":\"offline_fetch_shim\",\"outcome\":\"%s\",\"jobs\":%d,\"network_requests\":0}\n",good?"pass":"fail",jobs);
    JS_FreeValue(e.context,done);JS_FreeValue(e.context,global);return destroy(&e,"smoke")&&good;
}
int main(int argc,char **argv) {
    struct rlimit core={0,0};if(setrlimit(RLIMIT_CORE,&core))return 70;setvbuf(stdout,NULL,_IOLBF,0);
    if(argc<2)return 64;int good=0;double started=now();
    printf("{\"phase\":\"runtime\",\"version\":\"%s\",\"engine\":\"QuickJS-NG\",\"core_dumps\":false}\n",JS_GetVersion());
    if(!strcmp(argv[1],"full-parse")&&argc==5)good=extract(argv[2],argv[3],argv[4],true);
    else if(!strcmp(argv[1],"reduced-extract")&&argc==5)good=extract(argv[2],argv[3],argv[4],false);
    else if(!strcmp(argv[1],"oom"))good=resource_test(false);
    else if(!strcmp(argv[1],"cancel"))good=resource_test(true);
    else if(!strcmp(argv[1],"context-oom"))good=context_failure();
    else if(!strcmp(argv[1],"fetch-smoke")&&argc==3)good=smoke(argv[2]);
    else return 64;
    struct rusage usage;getrusage(RUSAGE_SELF,&usage);
    printf("{\"phase\":\"summary\",\"outcome\":\"%s\",\"elapsed_ms\":%.0f,\"process_maxrss_bytes\":%ld}\n",good?"pass":"fail",(now()-started)*1000,usage.ru_maxrss);
    return good?0:1;
}
