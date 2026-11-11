// MIT. Exercise the generic helper beyond the original four-second fixtures.
#include "muses_decode_probe.h"
#include <cstdio>
#include <string>
static int policy(const char*url,void*){return std::string(url).rfind("http://127.0.0.1:",0)==0;}
int main(int argc,char**argv){if(argc!=3)return 1;
    for(const char*name:{"aac-44100-40s.m4a","opus-48000-40s.webm"})for(double start:{0.0,30.0}){
        std::string url=std::string(argv[1])+"/"+name,path=std::string(argv[2])+"/"+name;
        MTDescriptor descriptor={1,MT_DIRECT,url.c_str(),nullptr,0,0,0};MTLimits transport={16ull<<20,16ull<<20,65536,512,2000,1,128ull<<20};MTStatus status;
        MTHandle*handle=mt_create(&descriptor,&transport,policy,nullptr,&status);if(!handle)return 2;
        MDProbeLimits limits={start,48000ull*900,60000};MDProbeReport report;int result=md_compare_native_to_file(handle,path.c_str(),&limits,&report);mt_destroy(handle);
        printf("{\"fixture\":\"%s\",\"seek_seconds\":%.0f,\"status\":%d,\"local_error\":%d,\"native_error\":%d,\"transport_status\":%d,\"equal_pcm\":%d,\"frames\":%llu,\"nonzero_samples\":%llu,\"rms\":%.9f,\"source_rate\":%u,\"pcm_sha256\":\"%s\",\"rss_high\":%llu}\n",name,start,result,report.local.ffmpeg_error,report.native.ffmpeg_error,report.transport.status,report.equal_pcm,report.native.output_frames,report.native.nonzero_samples,report.native.rms,report.native.source_sample_rate,report.native.pcm_sha256,report.transport.resident_high_bytes);
        uint64_t expected=start?480000:1920000;
        if(result||!report.equal_pcm||!report.native.nonzero_samples||report.native.rms<.04||report.native.output_frames+96<expected||report.native.output_frames>expected+96)return 3;
    }return 0;
}
