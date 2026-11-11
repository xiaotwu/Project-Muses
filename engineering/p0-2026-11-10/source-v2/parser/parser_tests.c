// SPDX-License-Identifier: MIT
#include "p0_parser.h"
#include <tree_sitter/api.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <time.h>
extern void *(*ts_current_malloc)(size_t);
static const char *fixture="var namespace={};(function(g){var unused=function(){return 'discarded';};var required=function(x){var re=/[{};\\/]/g;var t=`brace${x}`;return x.replace(re,t);};var solver;solver=function(a,b='',c=''){c=required(c);a=new g.URL(a,true);a.set('alr','yes');return a;};var timestamp=function(){return {signatureTimestamp:20760};};g.URL=function(a){this.a=a;};g.URL.prototype.set=function(a,b){return b;};})(namespace);";
static unsigned checks=0;
#define CHECK(value) do{checks++;if(!(value)){printf("{\"failed_check_line\":%d}\n",__LINE__);return 1;}}while(0)
static uint64_t ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
static int cancel_after_checks(void *opaque){unsigned *checks=opaque;return ++*checks>=5;}
static int cancel_when_output_ready(void *opaque){return ((p0_parser_result *)opaque)->output_bytes>0;}
static int recovery(void){
  char out[262145];p0_parser_result r;p0_parser_limits l={0};void *(*before)(size_t)=ts_current_malloc;
  for(unsigned i=0;i<12;i++){
    l.max_working_bytes=2048;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_MEMORY_LIMIT);CHECK(r.live_working_bytes==0&&out[0]==0);CHECK(ts_current_malloc==before);
    l.max_working_bytes=0;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_OK);CHECK(r.live_working_bytes==0);CHECK(strstr(out,"required=function")&&strstr(out,"var solver;")&&!strstr(out,"unused=function"));CHECK(ts_current_malloc==before);
  }
  const char *bad[]={"", "var a={};(function(g){", "(function(g){ var a=\"unterminated; })(x);", "var x={};(function(g){var a=/unterminated;})(x);", "var x={};(function(g){var a=(; })(x);"};
  for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){CHECK(p0_player_reduce(bad[i],strlen(bad[i]),&l,out,sizeof(out),&r)!=P0_PARSE_OK);CHECK(r.live_working_bytes==0);CHECK(ts_current_malloc==before);CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_OK);}
  l.max_input_bytes=8;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_INPUT_LIMIT);l.max_input_bytes=0;
  l.max_output_bytes=16;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_OUTPUT_LIMIT);l.max_output_bytes=0;
  volatile sig_atomic_t cancel=1;l.cancelled=&cancel;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_CANCELLED);l.cancelled=NULL;
  l.deadline_ns=ns()-1;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_DEADLINE);l.deadline_ns=0;
  unsigned cancellation_checks=0;l.should_cancel=cancel_after_checks;l.cancel_context=&cancellation_checks;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_CANCELLED);CHECK(cancellation_checks>=5&&r.live_working_bytes==0);l.should_cancel=NULL;l.cancel_context=NULL;
  CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_OK);CHECK(ts_current_malloc==before);
  l.should_cancel=cancel_when_output_ready;l.cancel_context=&r;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_CANCELLED);CHECK(r.live_working_bytes==0&&r.output_bytes==0&&out[0]==0&&ts_current_malloc==before);l.should_cancel=NULL;l.cancel_context=NULL;CHECK(p0_player_reduce(fixture,strlen(fixture),&l,out,sizeof(out),&r)==P0_PARSE_OK);
  // One selected function crosses the 64 KiB syntax window. Its embedded
  // delimiters remain string content; a recovered EOF is never a boundary.
  const char *head="var namespace={};(function(g){var longHelper=function(x){var text='";
  const char *tail="';return x+text;};var solver;solver=function(a,b='',c=''){c=longHelper(c);a=new g.URL(a,true);a.set('alr','yes');return a;};var stamp=function(){return {signatureTimestamp:20760};};g.URL=function(a){this.a=a;};})(namespace);";
  size_t padding=70000,total=strlen(head)+padding+strlen(tail);char *large=malloc(total+1);CHECK(large);strcpy(large,head);memset(large+strlen(head),'}',padding);strcpy(large+strlen(head)+padding,tail);
  CHECK(p0_player_reduce(large,total,&l,out,sizeof(out),&r)==P0_PARSE_OK);CHECK(r.output_bytes>padding&&strstr(out,"longHelper=function")&&r.live_working_bytes==0);free(large);
  return 0;
}
static atomic_int ready=0,start=0;
typedef struct {const char *input;size_t size;p0_parser_status status;size_t live;} Thread;
static void *work(void *opaque){Thread *t=opaque;char *out=malloc(262145);p0_parser_result r;atomic_fetch_add(&ready,1);while(!atomic_load(&start)){}t->status=p0_player_reduce(t->input,t->size,NULL,out,262145,&r);t->live=r.live_working_bytes;free(out);return NULL;}
int main(int argc,char **argv){
  if(recovery())return 1;
  if(argc>1){FILE *f=fopen(argv[1],"rb");CHECK(f);fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);CHECK(n>0&&n<=4*1024*1024);char *input=malloc(n+1);CHECK(input);CHECK(fread(input,1,n,f)==(size_t)n);fclose(f);input[n]=0;
    Thread data[8];pthread_t threads[8];for(int i=0;i<8;i++){data[i]=(Thread){input,(size_t)n,0,0};CHECK(!pthread_create(&threads[i],NULL,work,&data[i]));}while(atomic_load(&ready)!=8){}atomic_store(&start,1);unsigned pass=0,busy=0;for(int i=0;i<8;i++){pthread_join(threads[i],NULL);pass+=data[i].status==P0_PARSE_OK;busy+=data[i].status==P0_PARSE_BUSY;CHECK(data[i].live==0);}CHECK(pass>=1&&busy>=1&&pass+busy==8);free(input);
  }
  printf("{\"native_lifecycle_checks\":%u,\"outcome\":\"pass\",\"cap_then_valid_repetitions\":12,\"malformed_then_valid_cases\":5,\"concurrent_rejection_test\":%s}\n",checks,argc>1?"true":"false");return 0;
}
