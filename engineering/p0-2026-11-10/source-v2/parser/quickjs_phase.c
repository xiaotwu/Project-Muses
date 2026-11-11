// SPDX-License-Identifier: MIT
#include "quickjs.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>
#include <sys/resource.h>
#include <CommonCrypto/CommonDigest.h>
typedef struct{size_t size;size_t alignment;} Header;
typedef struct{size_t peak;double deadline;} Stats;
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static void *allocate(JSMallocState *s,size_t n){size_t total=n+sizeof(Header);if(total<n||total>s->malloc_limit-s->malloc_size)return NULL;Header *p=malloc(total);if(!p)return NULL;p->size=n;s->malloc_size+=total;s->malloc_count++;Stats *stats=s->opaque;if(s->malloc_size>stats->peak)stats->peak=s->malloc_size;return p+1;}
static void release(JSMallocState *s,void *p){if(!p)return;Header *h=(Header *)p-1;s->malloc_size-=h->size+sizeof(*h);s->malloc_count--;free(h);}
static void *resize(JSMallocState *s,void *p,size_t n){if(!p)return allocate(s,n);if(!n){release(s,p);return NULL;}Header *h=(Header *)p-1;size_t old=h->size,total=n+sizeof(*h);if(total<n||n>s->malloc_limit-s->malloc_size+old)return NULL;h=realloc(h,total);if(!h)return NULL;h->size=n;s->malloc_size=s->malloc_size-old+n;Stats *stats=s->opaque;if(s->malloc_size>stats->peak)stats->peak=s->malloc_size;return h+1;}
static size_t usable(const void *p){return p?((const Header *)p)[-1].size:0;}
static const JSMallocFunctions allocator={allocate,release,resize,usable};
static int interrupt(JSRuntime *rt,void *opaque){(void)rt;return now()>((Stats *)opaque)->deadline;}
static Stats outer;
static JSValue mark(JSContext *c,JSValueConst self,int argc,JSValueConst *argv){(void)self;(void)argc;const char *name=JS_ToCString(c,argv[0]);JSMemoryUsage u;JS_ComputeMemoryUsage(JS_GetRuntime(c),&u);struct rusage r;getrusage(RUSAGE_SELF,&r);printf("{\"phase\":\"%s\",\"js_live_bytes\":%lld,\"js_peak_bytes\":%zu,\"process_maxrss_bytes\":%ld}\n",name?name:"unknown",(long long)u.malloc_size,outer.peak,r.ru_maxrss);fflush(stdout);JS_FreeCString(c,name);return JS_UNDEFINED;}
static JSValue gc(JSContext *c,JSValueConst self,int argc,JSValueConst *argv){(void)self;(void)argc;(void)argv;JS_RunGC(JS_GetRuntime(c));return JS_UNDEFINED;}
static char *read_file(const char *path,size_t limit,size_t *size){FILE *f=fopen(path,"rb");if(!f)return NULL;fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);if(n<0||(size_t)n>limit){fclose(f);return NULL;}char *p=malloc(n+1);if(p){*size=fread(p,1,n,f);p[*size]=0;}fclose(f);return p;}
static void digest(const char *s,size_t n,char out[65]){unsigned char hash[CC_SHA256_DIGEST_LENGTH];CC_SHA256(s,(CC_LONG)n,hash);for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)sprintf(out+i*2,"%02x",hash[i]);}
static void exception(JSContext *c,const char *phase){JSValue e=JS_GetException(c);JSValue name=JS_GetPropertyStr(c,e,"name"),message=JS_GetPropertyStr(c,e,"message");const char *n=JS_ToCString(c,name),*m=JS_ToCString(c,message);const char *category=m&&strstr(m,"out of memory")?"memory_limit":m&&strstr(m,"interrupted")?"deadline":m&&strstr(m,"is not defined")?"missing_dependency":"redacted";printf("{\"phase\":\"%s\",\"outcome\":\"fail\",\"error_name\":\"%s\",\"error_category\":\"%s\"}\n",phase,n?n:"unknown",category);JS_FreeCString(c,n);JS_FreeCString(c,m);JS_FreeValue(c,name);JS_FreeValue(c,message);JS_FreeValue(c,e);}
int main(int argc,char **argv){
  if(argc<5)return 64;size_t bundle_n=0,input_n=0;char *bundle=read_file(argv[1],4*1024*1024,&bundle_n),*input=read_file(argv[2],4*1024*1024,&input_n);if(!bundle||!input)return 65;
  outer.deadline=now()+15;JSRuntime *rt=JS_NewRuntime2(&allocator,&outer);JS_SetMemoryLimit(rt,64*1024*1024);JS_SetMaxStackSize(rt,1024*1024);JS_SetInterruptHandler(rt,interrupt,&outer);JSContext *c=JS_NewContext(rt);JSValue g=JS_GetGlobalObject(c);
  JS_SetPropertyStr(c,g,"nativeMark",JS_NewCFunction(c,mark,"nativeMark",1));JS_SetPropertyStr(c,g,"nativeGC",JS_NewCFunction(c,gc,"nativeGC",0));JS_SetPropertyStr(c,g,"playerSource",JS_NewStringLen(c,input,input_n));JS_SetPropertyStr(c,g,"PROBE_PHASE",JS_NewString(c,argv[4]));free(input);
  JSValue result=JS_Eval(c,bundle,bundle_n,"extraction.js",JS_EVAL_TYPE_GLOBAL);free(bundle);int code=0;
  if(JS_IsException(result)){exception(c,"main");code=1;}
  else if(strcmp(argv[4],"parse_only")){
    JSValue solver=JS_GetPropertyStr(c,g,"solverText"),test=JS_GetPropertyStr(c,g,"testText"),timestamp=JS_GetPropertyStr(c,g,"signatureTimestamp");size_t solver_n=0,test_n=0;const char *text=JS_ToCStringLen(c,&solver_n,solver),*test_s=JS_ToCStringLen(c,&test_n,test);int32_t stamp=0;JS_ToInt32(c,&stamp,timestamp);
    if(!text||solver_n>256*1024||!test_s){code=2;}else{
      FILE *f=fopen(argv[3],"wb");if(!f)code=3;else{fwrite(text,1,solver_n,f);fclose(f);}char sha[65];digest(text,solver_n,sha);printf("{\"phase\":\"solver_output\",\"bytes\":%zu,\"sha256\":\"%s\",\"signature_timestamp\":%d}\n",solver_n,sha,stamp);
      Stats inner={0,now()+1};JSRuntime *isolate=JS_NewRuntime2(&allocator,&inner);JS_SetMemoryLimit(isolate,8*1024*1024);JS_SetMaxStackSize(isolate,512*1024);JS_SetInterruptHandler(isolate,interrupt,&inner);JSContext *ic=JS_NewContext(isolate);
      char *wrapped=malloc(test_n+32);sprintf(wrapped,"(function(){%s})()",test_s);JSValue value=JS_Eval(ic,wrapped,strlen(wrapped),"isolated-solver.js",JS_EVAL_TYPE_GLOBAL);free(wrapped);
      if(JS_IsException(value)){exception(ic,"isolated_solver");code=4;}else{JSValue nv=JS_GetPropertyStr(ic,value,"n"),sv=JS_GetPropertyStr(ic,value,"sig");size_t nn=0,sn=0;const char *ns=JS_ToCStringLen(ic,&nn,nv),*ss=JS_ToCStringLen(ic,&sn,sv);bool valid=JS_IsString(nv)&&nn>0&&strncmp(ns,"enhanced_except_",16)&&JS_IsString(sv)&&sn>0;printf("{\"phase\":\"isolated_solver\",\"outcome\":\"%s\",\"n_length\":%zu,\"sig_length\":%zu,\"js_peak_bytes\":%zu,\"heap_limit_bytes\":8388608}\n",valid?"pass":"fail",nn,sn,inner.peak);if(!valid)code=5;JS_FreeCString(ic,ns);JS_FreeCString(ic,ss);JS_FreeValue(ic,nv);JS_FreeValue(ic,sv);}
      JS_FreeValue(ic,value);JS_FreeContext(ic);JS_FreeRuntime(isolate);
    }
    JS_FreeCString(c,text);JS_FreeCString(c,test_s);JS_FreeValue(c,solver);JS_FreeValue(c,test);JS_FreeValue(c,timestamp);
  }
  JS_FreeValue(c,result);JS_FreeValue(c,g);JS_FreeContext(c);JS_FreeRuntime(rt);struct rusage r;getrusage(RUSAGE_SELF,&r);printf("{\"phase\":\"summary\",\"main_js_peak_bytes\":%zu,\"main_heap_limit_bytes\":67108864,\"process_maxrss_bytes\":%ld}\n",outer.peak,r.ru_maxrss);return code;
}
