// SPDX-License-Identifier: MIT
// Include the frozen corrected host and observe its real input helper.
#include "quickjs.h"
static JSValue VerifyEval(JSContext *,const char *,size_t,const char *,int);
#define JS_Eval VerifyEval
#define main P0OriginalMain
#include "NativeHost.v2.m"
#undef main
#undef JS_Eval
#include <sys/resource.h>

static unsigned Checks,Failures,MainCalls,IsolatedCalls,BlockedRequests,TerminatorFailures;
static const char *Category="none",*Placement;
static size_t ObservedEvalHeap;
static const char *Classify(JSContext *ctx,JSValue exception) {
    if(JS_IsNull(exception))return "null_exception";
    if(!JS_IsError(ctx,exception))return "non_error_exception";
    // Frozen offline code only; retain fixed type categories, never raw text.
    JSValue name=JS_GetPropertyStr(ctx,exception,"name");const char *n=JS_ToCString(ctx,name);
    const char *category="other_error";
    if(n&&!strcmp(n,"SyntaxError"))category="syntax_error";
    else if(n&&!strcmp(n,"RangeError"))category="range_error";
    else if(n&&!strcmp(n,"InternalError"))category="internal_error";
    else if(n&&!strcmp(n,"ReferenceError"))category="reference_error";
    else if(n&&!strcmp(n,"TypeError"))category="type_error";
    JS_FreeCString(ctx,n);JS_FreeValue(ctx,name);return category;
}
static JSValue BlockNetwork(JSContext *ctx,JSValueConst self,int argc,JSValueConst *argv) {
    (void)ctx;(void)self;(void)argc;(void)argv;
    BlockedRequests++;finished=YES;resultCode=0;return JS_UNDEFINED;
}
static JSValue VerifyEval(JSContext *ctx,const char *input,size_t length,const char *filename,int flags) {
    // The helper owns length+1 bytes, so this is an in-bounds contract assertion.
    if(!input||input[length]!=0){TerminatorFailures++;return JS_ThrowInternalError(ctx,"invalid_test_input");}
    if(!strcmp(filename,"p0.bundle.js")){
        MainCalls++;JSValue global=JS_GetGlobalObject(ctx);
        JS_SetPropertyStr(ctx,global,"nativeRequest",JS_NewCFunction(ctx,BlockNetwork,"nativeRequest",1));JS_FreeValue(ctx,global);
    }else if(!strcmp(filename,"isolated-player.js"))IsolatedCalls++;
    JSValue result=JS_Eval(ctx,input,length,filename,flags);
    JSMemoryUsage memory;JS_ComputeMemoryUsage(JS_GetRuntime(ctx),&memory);
    ObservedEvalHeap=MAX(ObservedEvalHeap,(size_t)memory.malloc_size);
    if(JS_IsException(result)){JSValue error=JS_GetException(ctx);Category=Classify(ctx,error);JS_Throw(ctx,error);}
    return result;
}
static bool Check(bool good,const char *name) {
    Checks++;if(!good)Failures++;
    Output(JSONString(@{@"gate":@"input_contract_case",@"case":@(name),@"outcome":good?@"pass":@"fail",@"exception_category":@(Category)}));return good;
}
static NSData *NonTerminated(NSData *source,unsigned char trailer) {
    char *bytes=malloc(source.length+64);if(!bytes)return nil;
    memcpy(bytes,source.bytes,source.length);memset(bytes+source.length,trailer,64);
    return [NSData dataWithBytesNoCopy:bytes length:source.length freeWhenDone:YES];
}
static bool HelperCase(const char *name,NSData *data,const char *expectedType,const char *expectedValue) {
    if(!P0V2BeginOperation(1))return Check(false,name);
    JSRuntime *rt=JS_NewRuntime();if(!rt){P0V2EndOperation();return Check(false,name);}
    JS_SetMemoryLimit(rt,8*1024*1024);JSContext *ctx=JS_NewContext(rt);
    if(!ctx){JS_FreeRuntime(rt);P0V2EndOperation();return Check(false,name);}
    Category="none";JSValue value=P0EvaluateData(ctx,data,"helper-fixture.js",JS_EVAL_TYPE_GLOBAL);
    bool good;
    if(expectedType){JSValue error=JS_GetException(ctx);Category=Classify(ctx,error);good=JS_IsException(value)&&!strcmp(Category,expectedType);JS_FreeValue(ctx,error);}
    else {const char *text=JS_ToCString(ctx,value);good=!JS_IsException(value)&&text&&!strcmp(text,expectedValue);JS_FreeCString(ctx,text);}
    good=good&&!V2ShouldStop();JS_FreeValue(ctx,value);JS_FreeContext(ctx);JS_FreeRuntime(rt);P0V2EndOperation();
    return Check(good,name);
}
static bool Helpers(void) {
    bool good=true;NSData *expression=[@"1+2" dataUsingEncoding:NSUTF8StringEncoding];
    good&=HelperCase("nil_rejected",nil,"internal_error",NULL);
    good&=HelperCase("empty_valid",[NSData data],NULL,"undefined");
    good&=HelperCase("non_nul_at",NonTerminated(expression,'@'),NULL,"3");
    good&=HelperCase("non_nul_brace",NonTerminated(expression,'}'),NULL,"3");
    good&=HelperCase("utf8_bytes",NonTerminated([@"'π🎵'" dataUsingEncoding:NSUTF8StringEncoding],'@'),NULL,"π🎵");
    good&=HelperCase("invalid_script_preserved",[@"@" dataUsingEncoding:NSUTF8StringEncoding],"syntax_error",NULL);
    NSMutableData *limit=[NSMutableData dataWithLength:4*1024*1024];memset(limit.mutableBytes,' ',limit.length);((char *)limit.mutableBytes)[0]='7';
    good&=HelperCase("exact_4mib",NonTerminated(limit,'@'),NULL,"7");
    [limit increaseLengthBy:1];good&=HelperCase("above_4mib_rejected",limit,"range_error",NULL);
    return good;
}
typedef struct { const char *path;unsigned count;bool fixture;bool good; } Job;
static void *RunHost(void *arg) {
    Job *job=arg;job->good=true;
    @autoreleasepool {
        V2Client=@"TV_SAMSUNG";V2Codec=@"aac";
        for(unsigned i=0;i<job->count;i++){
            unsigned before=MainCalls,prior=BlockedRequests,inner=IsolatedCalls;Category="none";double start=Now();
            if(!P0V2BeginOperation(2)){job->good=false;break;}
            int code=RunProof(@(job->path),i%2?@"resolve_next":@"resolve_first");NSString *reason=V2StopReason();
            bool good=code==0&&[reason isEqual:@"none"]&&MainCalls==before+1&&context==NULL&&runtime==NULL&&bridge==nil;
            good=good&&(job->fixture?(IsolatedCalls==inner+1&&BlockedRequests==prior):(BlockedRequests==prior+1));
            P0V2EndOperation();Checks++;if(!good)Failures++;job->good&=good;
            Output(JSONString(@{@"gate":@"corrected_host_case",@"iteration":@(i),@"fixture":@(job->fixture),@"placement":@(Placement),@"outcome":good?@"pass":@"fail",@"exception_category":@(Category),@"code":@(code),@"elapsed_ms":@((Now()-start)*1000),@"js_peak_allocated_bytes":@(peakAllocated),@"native_stack_bytes":@(pthread_get_stacksize_np(pthread_self())),@"blocked_request_calls":@(BlockedRequests-prior)}));
        }
    }return NULL;
}
static bool Isolated(void) {
    bool good=true;
    for(unsigned i=0;i<12;i++){
        Category="none";if(!P0V2BeginOperation(1))return Check(false,"isolated_begin");
        NSString *result=P0IsolatedEvaluate(@"return {answer:42,label:'π🎵'};");
        NSDictionary *value=result?[NSJSONSerialization JSONObjectWithData:[result dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil]:nil;
        bool ok=[value[@"answer"] intValue]==42&&[value[@"label"] isEqual:@"π🎵"]&&!V2ShouldStop();P0V2EndOperation();good&=Check(ok,"isolated_repeat");
    }
    Category="none";if(!P0V2BeginOperation(.05))return Check(false,"isolated_deadline_begin");
    NSString *result=P0IsolatedEvaluate(@"for(;;){}");bool stopped=result==nil&&[V2StopReason() isEqual:@"deadline"];P0V2EndOperation();good&=Check(stopped,"isolated_deadline");
    Category="none";if(!P0V2BeginOperation(1))return Check(false,"isolated_recovery_begin");
    result=P0IsolatedEvaluate(@"return 42;");bool recovered=[result isEqual:@"42"]&&!V2ShouldStop();P0V2EndOperation();good&=Check(recovered,"isolated_fresh_after_deadline");
    return good;
}
int main(int argc,char **argv) {
    struct rlimit core={0,0};if(setrlimit(RLIMIT_CORE,&core)||argc!=5)return 64;setvbuf(stdout,NULL,_IOLBF,0);
    @autoreleasepool {
        Placement=argv[2];const char *mode=argv[3];unsigned count=(unsigned)atoi(argv[4]);bool good=false;
        if(!strcmp(mode,"helpers"))good=Helpers();
        else if(!strcmp(mode,"isolated"))good=Isolated();
        else {
            Job job={argv[1],count,!strcmp(mode,"fixture"),false};if(count<1||count>12)return 64;
            if(!strcmp(Placement,"main"))RunHost(&job);
            else if(!strcmp(Placement,"dispatch")){
                dispatch_queue_t queue=dispatch_queue_create("org.muses.p0.corrected-init",DISPATCH_QUEUE_SERIAL);dispatch_semaphore_t done=dispatch_semaphore_create(0);__block bool all=true;
                for(unsigned i=0;i<count;i++)dispatch_async(queue,^{Job one={job.path,1,job.fixture,false};RunHost(&one);all&=one.good;dispatch_semaphore_signal(done);});
                for(unsigned i=0;i<count;i++)dispatch_semaphore_wait(done,DISPATCH_TIME_FOREVER);job.good=all;
            }else{
                pthread_attr_t attributes;pthread_attr_init(&attributes);if(pthread_attr_setstacksize(&attributes,512*1024))return 65;
                pthread_t thread;if(pthread_create(&thread,&attributes,RunHost,&job))return 66;pthread_attr_destroy(&attributes);pthread_join(thread,NULL);
            }good=job.good;
        }
        struct rusage usage;getrusage(RUSAGE_SELF,&usage);good=good&&TerminatorFailures==0&&Failures==0;
        Output(JSONString(@{@"gate":@"corrected_input_summary",@"outcome":good?@"pass":@"fail",@"checks":@(Checks),@"failures":@(Failures),@"main_eval_calls":@(MainCalls),@"isolated_eval_calls":@(IsolatedCalls),@"terminator_failures":@(TerminatorFailures),@"network_requests":@0,@"blocked_request_calls":@(BlockedRequests),@"observed_eval_heap_bytes":@(ObservedEvalHeap),@"process_maxrss_bytes":@(usage.ru_maxrss)}));return good?0:1;
    }
}
