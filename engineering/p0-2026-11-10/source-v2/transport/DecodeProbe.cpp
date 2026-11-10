// MIT. Isolated P0 comparison; source URLs are never passed to FFmpeg logging.
#include "muses_decode_probe.h"
#include <CommonCrypto/CommonDigest.h>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libswresample/swresample.h>
}
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdio>
#include <sys/stat.h>
#include <thread>

namespace {
using Clock=std::chrono::steady_clock;
constexpr int rate=48000;
void require(bool condition,int error=AVERROR_INVALIDDATA){if(!condition)throw error;}
struct Input {
    MTHandle *handle=nullptr;uint64_t position=0,total=0;Clock::time_point deadline;
    static int interrupt(void*p){return Clock::now()>static_cast<Input*>(p)->deadline;}
    static int read(void*p,uint8_t*buffer,int size){auto&s=*static_cast<Input*>(p);if(interrupt(p))return AVERROR_EXIT;
        size_t got=0;auto status=mt_read_at(s.handle,s.position,buffer,size,&got);if(status==MT_EOF)return AVERROR_EOF;
        if(status==MT_CANCELLED)return AVERROR_EXIT;if(status!=MT_OK)return AVERROR(EIO);s.position+=got;return int(got);}
    static int64_t seek(void*p,int64_t offset,int origin){auto&s=*static_cast<Input*>(p);if(origin==AVSEEK_SIZE)return s.total;
        origin&=~AVSEEK_FORCE;int64_t next=offset;if(origin==SEEK_CUR)next+=s.position;else if(origin==SEEK_END)next+=s.total;else if(origin!=SEEK_SET)return AVERROR(EINVAL);
        if(next<0||uint64_t(next)>s.total)return AVERROR(EINVAL);s.position=next;return next;}
};
struct Watchdog {
    std::atomic<bool>finished{false};std::thread worker;
    Watchdog(MTHandle*handle,Clock::time_point deadline){if(handle)worker=std::thread([this,handle,deadline]{while(!finished&&Clock::now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(20));if(!finished)mt_cancel(handle);});}
    ~Watchdog(){finished=true;if(worker.joinable())worker.join();}
};
struct Decoder {
    AVFormatContext*format=avformat_alloc_context();AVCodecContext*codec=nullptr;AVIOContext*io=nullptr;
    AVFrame*frame=av_frame_alloc();AVPacket*packet=av_packet_alloc();SwrContext*swr=nullptr;
    ~Decoder(){av_frame_free(&frame);av_packet_free(&packet);swr_free(&swr);avcodec_free_context(&codec);avformat_close_input(&format);if(io){av_freep(&io->buffer);avio_context_free(&io);}}
};
void decode(MTHandle*handle,const char*path,const MDProbeLimits&limits,MDDecodeStats&out){
    Input source{handle,0,0,Clock::now()+std::chrono::milliseconds(limits.timeout_ms)};
    Watchdog deadline(handle,source.deadline);Decoder d;out.first_output_seconds=-1;
    try{
        require(d.format&&d.frame&&d.packet,AVERROR(ENOMEM));
        d.format->probesize=65536;d.format->max_analyze_duration=AV_TIME_BASE;d.format->max_streams=4;
        d.format->interrupt_callback={Input::interrupt,&source};
        if(handle){uint8_t first;size_t got=0;require(mt_read_at(handle,0,&first,1,&got)==MT_OK&&got==1,AVERROR(EIO));
            MTStats stats;mt_snapshot(handle,&stats);source.total=stats.total_bytes;require(source.total>0&&source.total<=16ull*1024*1024);
            d.io=avio_alloc_context(static_cast<uint8_t*>(av_malloc(4096)),4096,0,&source,Input::read,nullptr,Input::seek);
            require(d.io,AVERROR(ENOMEM));d.io->seekable=AVIO_SEEKABLE_NORMAL;d.format->pb=d.io;d.format->flags|=AVFMT_FLAG_CUSTOM_IO;}
        int result=avformat_open_input(&d.format,handle?nullptr:path,nullptr,nullptr);require(result>=0,result);
        result=avformat_find_stream_info(d.format,nullptr);require(result>=0,result);
        int stream=av_find_best_stream(d.format,AVMEDIA_TYPE_AUDIO,-1,-1,nullptr,0);require(stream>=0,stream);
        auto*parameters=d.format->streams[stream]->codecpar;
        require(parameters->codec_id==AV_CODEC_ID_AAC||parameters->codec_id==AV_CODEC_ID_OPUS,AVERROR_DECODER_NOT_FOUND);
        d.codec=avcodec_alloc_context3(avcodec_find_decoder(parameters->codec_id));require(d.codec,AVERROR(ENOMEM));
        result=avcodec_parameters_to_context(d.codec,parameters);require(result>=0,result);
        d.codec->pkt_timebase=d.format->streams[stream]->time_base;d.codec->thread_count=1;
        result=avcodec_open2(d.codec,d.codec->codec,nullptr);require(result>=0,result);
        require(d.codec->sample_rate>=8000&&d.codec->sample_rate<=192000&&d.codec->ch_layout.nb_channels>=1&&d.codec->ch_layout.nb_channels<=8);
        out.source_sample_rate=d.codec->sample_rate;out.source_channels=d.codec->ch_layout.nb_channels;out.codec_id=parameters->codec_id;
        AVChannelLayout stereo=AV_CHANNEL_LAYOUT_STEREO;
        result=swr_alloc_set_opts2(&d.swr,&stereo,AV_SAMPLE_FMT_FLT,rate,&d.codec->ch_layout,d.codec->sample_fmt,d.codec->sample_rate,0,nullptr);require(result>=0,result);
        result=swr_init(d.swr);require(result>=0,result);
        const double timebase=av_q2d(d.format->streams[stream]->time_base);
        const double duration=d.format->streams[stream]->duration==AV_NOPTS_VALUE?INFINITY:d.format->streams[stream]->duration*timebase;
        if(limits.start_seconds>0){auto target=int64_t(std::max(0.0,limits.start_seconds-.12)/timebase);
            result=avformat_seek_file(d.format,stream,INT64_MIN,target,target,AVSEEK_FLAG_BACKWARD);require(result>=0,result);avcodec_flush_buffers(d.codec);}
        std::array<float,8192*2> converted{};CC_SHA256_CTX hash;CC_SHA256_Init(&hash);long double energy=0;double nextPTS=0;
        auto consume=[&](int count,double pts){
            require(Clock::now()<=source.deadline,AVERROR_EXIT);
            int begin=int(std::min(double(count),std::max(0.0,std::ceil((limits.start_seconds-pts)*rate-0.01))));
            int end=int(std::max(0.0,std::min(double(count),std::ceil((duration-pts)*rate-0.01))));
            if(begin<end){require(out.output_frames+uint64_t(end-begin)<=limits.max_output_frames,AVERROR(ENOBUFS));
                if(out.first_output_seconds<0)out.first_output_seconds=pts+double(begin)/rate;
                for(int i=begin*2;i<end*2;i++){require(std::isfinite(converted[i]));energy+=converted[i]*converted[i];if(std::abs(converted[i])>1e-8f)out.nonzero_samples++;}
                CC_SHA256_Update(&hash,converted.data()+begin*2,(CC_LONG)((end-begin)*2*sizeof(float)));out.output_frames+=end-begin;}
            nextPTS=pts+double(count)/rate;
        };
        auto receive=[&]{int code;
            while((code=avcodec_receive_frame(d.codec,d.frame))>=0){
                require(swr_get_out_samples(d.swr,d.frame->nb_samples)<=8192,AVERROR(ENOBUFS));
                double pts=d.frame->pts==AV_NOPTS_VALUE?nextPTS:d.frame->pts*timebase-double(swr_get_delay(d.swr,d.codec->sample_rate))/d.codec->sample_rate;
                uint8_t*output=reinterpret_cast<uint8_t*>(converted.data());
                int count=swr_convert(d.swr,&output,8192,const_cast<const uint8_t**>(d.frame->extended_data),d.frame->nb_samples);require(count>=0,count);
                consume(count,pts);av_frame_unref(d.frame);}
            require(code==AVERROR(EAGAIN)||code==AVERROR_EOF,code);
        };
        while((result=av_read_frame(d.format,d.packet))>=0){require(Clock::now()<=source.deadline,AVERROR_EXIT);
            if(d.packet->stream_index==stream){int code=avcodec_send_packet(d.codec,d.packet);require(code>=0,code);receive();}av_packet_unref(d.packet);}
        require(result==AVERROR_EOF,result);result=avcodec_send_packet(d.codec,nullptr);require(result>=0,result);receive();
        for(;;){uint8_t*output=reinterpret_cast<uint8_t*>(converted.data());int count=swr_convert(d.swr,&output,8192,nullptr,0);require(count>=0,count);if(!count)break;consume(count,nextPTS);}
        require(out.output_frames>0,AVERROR_EOF);
        unsigned char bytes[CC_SHA256_DIGEST_LENGTH];CC_SHA256_Final(bytes,&hash);for(int i=0;i<32;i++)snprintf(out.pcm_sha256+i*2,3,"%02x",bytes[i]);
        out.rms=out.output_frames?std::sqrt(double(energy/(out.output_frames*2))):0;
    }catch(int error){out.ffmpeg_error=error?error:AVERROR_UNKNOWN;}
    catch(...){out.ffmpeg_error=AVERROR_UNKNOWN;}
}
}
extern "C" int md_compare_native_to_file(MTHandle*handle,const char*path,const MDProbeLimits*limits,MDProbeReport*report){
    if(!report)return 1;*report={};
    if(!handle||!path||!limits||!std::isfinite(limits->start_seconds)||limits->start_seconds<0||limits->start_seconds>900||!limits->max_output_frames||limits->max_output_frames>48000ull*900||!limits->timeout_ms||limits->timeout_ms>60000)return report->error=1;
    // Isolated harness only: suppress FFmpeg's raw string diagnostics; numeric
    // errors and native transport status remain in the returned report.
    av_log_set_level(AV_LOG_QUIET);
    struct stat file;if(stat(path,&file)!=0||!S_ISREG(file.st_mode)||file.st_size<=0||file.st_size>16ll*1024*1024)return report->error=1;
    uint8_t first;size_t got=0;if(mt_read_at(handle,0,&first,1,&got)!=MT_OK||got!=1){mt_snapshot(handle,&report->transport);report->native.ffmpeg_error=AVERROR(EIO);return report->error=3;}
    mt_snapshot(handle,&report->transport);if(report->transport.total_bytes!=uint64_t(file.st_size)){report->local.ffmpeg_error=AVERROR_INVALIDDATA;return report->error=2;}
    try{decode(nullptr,path,*limits,report->local);}catch(...){report->local.ffmpeg_error=AVERROR(ENOMEM);return report->error=2;}
    if(report->local.ffmpeg_error)return report->error=2;
    try{decode(handle,nullptr,*limits,report->native);}catch(...){report->native.ffmpeg_error=AVERROR(ENOMEM);mt_snapshot(handle,&report->transport);return report->error=3;}mt_snapshot(handle,&report->transport);
    if(report->native.ffmpeg_error)return report->error=3;
    report->equal_pcm=report->local.output_frames==report->native.output_frames&&strcmp(report->local.pcm_sha256,report->native.pcm_sha256)==0;
    return report->error=report->equal_pcm?0:4;
}
