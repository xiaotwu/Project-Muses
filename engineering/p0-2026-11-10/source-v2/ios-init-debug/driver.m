// SPDX-License-Identifier: MIT
// Exact candidate-5 generated host; JS_Eval input instrumentation only.
#include "quickjs.h"
static JSValue DebugEval(JSContext *,const char *,size_t,const char *,int);
#define JS_Eval DebugEval
#define main P0OriginalMain
#include "NativeHost.v2.m"
#undef main
#undef JS_Eval
#include <stdio.h>
#include <sys/resource.h>

static const char *Tail,*Placement,*Mode,*Category;
static unsigned EvalCount,Failures,BlockedRequests;
static size_t LastInput,LastPeak;
static bool CompileOnly;
static JSValue BlockNetwork(JSContext *ctx,JSValueConst self,int argc,JSValueConst *argv) {
    (void)ctx;(void)self;(void)argc;(void)argv;
    BlockedRequests++;finished=YES;resultCode=0;return JS_UNDEFINED;
}
static const char *Classify(JSContext *ctx,JSValue exception) {
    if(JS_IsNull(exception))return "null_exception";
    if(!JS_IsError(ctx,exception))return "non_error_exception";
    JSMemoryUsage usage;JS_ComputeMemoryUsage(JS_GetRuntime(ctx),&usage);
    if(usage.malloc_size>60*1024*1024)return "allocation_pressure_uninspected";
    // Only built-in compiler/bootstrap errors from a frozen offline bundle.
    // No response payload or raw exception string is printed or saved.
    JSValue name=JS_GetPropertyStr(ctx,exception,"name"),message=JS_GetPropertyStr(ctx,exception,"message");
    const char *n=JS_ToCString(ctx,name),*m=JS_ToCString(ctx,message),*category="other_error";
    if(n&&!strcmp(n,"SyntaxError"))category=m&&strstr(m,"stack overflow")?"syntax_stack_overflow":"syntax_error";
    else if(n&&!strcmp(n,"RangeError"))category=m&&strstr(m,"stack overflow")?"range_stack_overflow":"range_error";
    else if(n&&!strcmp(n,"InternalError"))category=m&&strstr(m,"out of memory")?"internal_out_of_memory":m&&strstr(m,"interrupted")?"internal_interrupted":"internal_error";
    else if(n&&!strcmp(n,"ReferenceError"))category="reference_error";
    else if(n&&!strcmp(n,"TypeError"))category="type_error";
    JS_FreeCString(ctx,n);JS_FreeCString(ctx,m);JS_FreeValue(ctx,name);JS_FreeValue(ctx,message);return category;
}
static JSValue DebugEval(JSContext *ctx,const char *input,size_t length,const char *filename,int flags) {
    if(strcmp(filename,"p0.bundle.js"))return JS_Eval(ctx,input,length,filename,flags);
    EvalCount++;LastInput=length;Category="none";
    if(!input||!length||length>4*1024*1024){Category="invalid_native_input";Failures++;return JS_ThrowTypeError(ctx,"invalid offline input");}
    char *owned=NULL;const char *value=input;
    if(strcmp(Tail,"ndata")){
        owned=malloc(length+64);if(!owned){Category="native_allocation_failed";Failures++;return JS_ThrowOutOfMemory(ctx);}
        memcpy(owned,input,length);memset(owned+length,0,64);
        if(!strcmp(Tail,"at"))memcpy(owned+length,"@",1);
        else if(!strcmp(Tail,"brace"))memcpy(owned+length,"}",1);
        else if(!strcmp(Tail,"identifier"))memcpy(owned+length,"trailer",7);
        else if(!strcmp(Tail,"space"))memcpy(owned+length," ",1);
        value=owned;
    }
    // Replace only the actual host's networking function before executing any
    // bundle code. No native request task can be created by this driver.
    JSValue global=JS_GetGlobalObject(ctx);
    JS_SetPropertyStr(ctx,global,"nativeRequest",JS_NewCFunction(ctx,BlockNetwork,"nativeRequest",1));JS_FreeValue(ctx,global);
    JSValue result=JS_Eval(ctx,value,length,filename,flags|(CompileOnly?JS_EVAL_FLAG_COMPILE_ONLY:0));
    free(owned);LastPeak=peakAllocated;
    if(JS_IsException(result)){
        JSValue exception=JS_GetException(ctx);Category=Classify(ctx,exception);JS_Throw(ctx,exception);Failures++;
    }else if(CompileOnly){finished=YES;resultCode=0;}
    return result;
}
typedef struct {const char *path;unsigned repetitions;bool good;} Job;
static void *Run(void *argument) {
    Job *job=argument;job->good=true;
    @autoreleasepool {
        V2Client=@"TV_SAMSUNG";V2Codec=@"aac";
        for(unsigned i=0;i<job->repetitions;i++){
            unsigned old=EvalCount,prior=BlockedRequests;double before=Now();
            if(!P0V2BeginOperation(1)){job->good=false;break;}
            int result=RunProof(@(job->path),i%2?@"resolve_next":@"resolve_first");
            NSString *stop=V2StopReason();P0V2EndOperation();
            bool shape=EvalCount==old+1&&bridge==nil&&context==NULL&&runtime==NULL;
            bool expectedFailure=!strcmp(Tail,"at")||!strcmp(Tail,"brace");
            bool expected=expectedFailure ? result!=0&&!strcmp(Category,"syntax_error") : result==0&&!strcmp(Category,"none");
            if(!CompileOnly&&!expectedFailure)expected=expected&&BlockedRequests>prior;
            job->good=job->good&&shape&&expected&&[stop isEqual:@"none"];
            printf("{\"phase\":\"case\",\"iteration\":%u,\"tail\":\"%s\",\"placement\":\"%s\",\"mode\":\"%s\",\"input_bytes\":%zu,\"result\":%d,\"exception_category\":\"%s\",\"js_peak_bytes\":%zu,\"native_stack_bytes\":%zu,\"blocked_request_calls\":%u,\"elapsed_ms\":%.3f,\"shape_ok\":%s,\"expected\":%s}\n",i,Tail,Placement,Mode,LastInput,result,Category,LastPeak,pthread_get_stacksize_np(pthread_self()),BlockedRequests-prior,(Now()-before)*1000,shape?"true":"false",expected?"true":"false");
        }
    }
    return NULL;
}
int main(int argc,char **argv) {
    struct rlimit core={0,0};if(setrlimit(RLIMIT_CORE,&core)||argc!=6)return 64;setvbuf(stdout,NULL,_IOLBF,0);
    Mode=argv[2];CompileOnly=!strcmp(Mode,"compile");Tail=argv[3];Placement=argv[4];
    Job job={argv[1],(unsigned)atoi(argv[5]),false};if(job.repetitions<1||job.repetitions>20)return 64;
    if(!strcmp(Placement,"main"))Run(&job);
    else if(!strcmp(Placement,"dispatch")){
        dispatch_queue_t queue=dispatch_queue_create("org.muses.p0.init-debug",DISPATCH_QUEUE_SERIAL);
        dispatch_semaphore_t done=dispatch_semaphore_create(0);
        // Each turn returns to the serial queue before a fresh runtime begins.
        unsigned repetitions=job.repetitions;__block bool good=true;
        for(unsigned i=0;i<repetitions;i++)dispatch_async(queue,^{Job one={job.path,1,false};Run(&one);good=good&&one.good;dispatch_semaphore_signal(done);});
        for(unsigned i=0;i<repetitions;i++)dispatch_semaphore_wait(done,DISPATCH_TIME_FOREVER);job.good=good;
    }else{
        pthread_attr_t attributes;pthread_attr_init(&attributes);
        size_t size=!strcmp(Placement,"pthread512")?512*1024:2*1024*1024;
        if(pthread_attr_setstacksize(&attributes,size))return 65;
        pthread_t thread;if(pthread_create(&thread,&attributes,Run,&job))return 66;
        pthread_attr_destroy(&attributes);pthread_join(thread,NULL);
    }
    struct rusage usage;getrusage(RUSAGE_SELF,&usage);
    printf("{\"phase\":\"summary\",\"outcome\":\"%s\",\"evaluations\":%u,\"observed_exceptions\":%u,\"network_requests\":0,\"process_maxrss_bytes\":%ld}\n",job.good?"pass":"fail",EvalCount,Failures,usage.ru_maxrss);
    return job.good?0:1;
}
