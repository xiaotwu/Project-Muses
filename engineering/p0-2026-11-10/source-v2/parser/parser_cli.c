// SPDX-License-Identifier: MIT
#include "p0_parser.h"
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <string.h>
#include <time.h>
static uint64_t ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
int main(int argc,char **argv){
  if(argc<3)return 64;FILE *f=fopen(argv[1],"rb");if(!f)return 65;fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);if(n<0||n>4*1024*1024){fclose(f);return 66;}
  char *input=malloc((size_t)n+1),*output=malloc(256*1024+1);if(!input||!output)return 67;size_t read=fread(input,1,(size_t)n,f);fclose(f);if(read!=(size_t)n)return 68;input[n]=0;
  p0_parser_limits limits={0};limits.deadline_ns=ns()+10000000000ULL;
  if(argc>3)limits.max_working_bytes=strtoull(argv[3],NULL,10);
  p0_parser_result r;p0_parser_status status=p0_player_reduce(input,n,&limits,output,256*1024+1,&r);
  if(status==P0_PARSE_OK){f=fopen(argv[2],"wb");if(!f)return 69;fwrite(output,1,r.output_bytes,f);fclose(f);}
  struct rusage u;getrusage(RUSAGE_SELF,&u);
  if(status)printf("{\"failure_offset\":%u,\"parse_window_bytes\":%u}\n",r.failure_offset,r.parse_window_bytes);
  printf("{\"status\":\"%s\",\"input_bytes\":%zu,\"output_bytes\":%zu,\"native_peak_bytes\":%zu,\"native_live_after_bytes\":%zu,\"declarations\":%u,\"selected\":%u,\"solver_matches\":%u,\"timestamp_matches\":%u,\"parse_ms\":%.3f,\"reduce_ms\":%.3f,\"process_maxrss_bytes\":%ld}\n",p0_parser_status_name(status),r.input_bytes,r.output_bytes,r.peak_working_bytes,r.live_working_bytes,r.declarations,r.selected_declarations,r.solver_matches,r.timestamp_matches,r.parse_ns/1e6,r.reduce_ns/1e6,u.ru_maxrss);
  free(input);free(output);return status?1:0;
}
