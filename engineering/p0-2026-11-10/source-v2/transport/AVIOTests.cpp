// MIT. FFmpeg custom AVIO proof; media reads/seek/cancel stay in native transport.
#include "muses_transport.h"
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
}
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

static void require(bool ok,const char*message){if(!ok)throw std::runtime_error(message);}
static int policy(const char*url,void*){return std::string(url).rfind("http://127.0.0.1:",0)==0;}
struct Source{MTHandle*handle=nullptr;uint64_t position=0,total=0;~Source(){mt_destroy(handle);}};
static int readPacket(void*opaque,uint8_t*buffer,int size){auto&s=*static_cast<Source*>(opaque);size_t got=0;auto status=mt_read_at(s.handle,s.position,buffer,size,&got);if(status==MT_EOF)return AVERROR_EOF;if(status==MT_CANCELLED)return AVERROR_EXIT;if(status!=MT_OK)return AVERROR(EIO);s.position+=got;return int(got);}
static int64_t seekPacket(void*opaque,int64_t offset,int origin){auto&s=*static_cast<Source*>(opaque);if(origin==AVSEEK_SIZE)return int64_t(s.total);origin&=~AVSEEK_FORCE;int64_t next=offset;if(origin==SEEK_CUR)next+=s.position;else if(origin==SEEK_END)next+=s.total;else if(origin!=SEEK_SET)return AVERROR(EINVAL);if(next<0||uint64_t(next)>s.total)return AVERROR(EINVAL);s.position=next;return next;}

static std::vector<float> decode(const char*location,bool native,double seek,MTStats*out){
    Source source;AVIOContext*io=nullptr;AVFormatContext*format=avformat_alloc_context();
    AVCodecContext*codec=nullptr;AVFrame*frame=av_frame_alloc();AVPacket*packet=av_packet_alloc();
    std::vector<float> pcm;pcm.reserve(48000*5*2);
    try{
        format->probesize=65536;format->max_analyze_duration=AV_TIME_BASE;
        if(native){
            MTDescriptor descriptor={1,MT_DIRECT,location,nullptr,0,0,0};
            MTLimits limits={16ull<<20,16ull<<20,4096,512,2000,1,128ull<<20};MTStatus status;
            source.handle=mt_create(&descriptor,&limits,policy,nullptr,&status);require(source.handle,"native create");
            uint8_t first;size_t got;require(mt_read_at(source.handle,0,&first,1,&got)==MT_OK&&got==1,"native initial range");
            MTStats stats;mt_snapshot(source.handle,&stats);source.total=stats.total_bytes;
            io=avio_alloc_context(static_cast<unsigned char*>(av_malloc(4096)),4096,0,&source,readPacket,nullptr,seekPacket);
            require(io,"AVIO allocation");io->seekable=AVIO_SEEKABLE_NORMAL;format->pb=io;format->flags|=AVFMT_FLAG_CUSTOM_IO;
        }
        require(avformat_open_input(&format,native?nullptr:location,nullptr,nullptr)>=0,"format open");
        require(avformat_find_stream_info(format,nullptr)>=0,"stream info");
        int stream=av_find_best_stream(format,AVMEDIA_TYPE_AUDIO,-1,-1,nullptr,0);require(stream>=0,"audio stream");
        codec=avcodec_alloc_context3(avcodec_find_decoder(format->streams[stream]->codecpar->codec_id));
        require(avcodec_parameters_to_context(codec,format->streams[stream]->codecpar)>=0,"parameters");
        codec->pkt_timebase=format->streams[stream]->time_base;
        require(avcodec_open2(codec,codec->codec,nullptr)>=0,"codec open");
        require(codec->sample_rate==48000&&codec->ch_layout.nb_channels==2&&codec->sample_fmt==AV_SAMPLE_FMT_FLTP,"fixture format");
        auto timebase=av_q2d(format->streams[stream]->time_base);
        double duration=format->streams[stream]->duration==AV_NOPTS_VALUE?INFINITY:format->streams[stream]->duration*timebase;
        if(seek>0){auto target=int64_t((seek-.12)/timebase);require(avformat_seek_file(format,stream,INT64_MIN,target,target,AVSEEK_FLAG_BACKWARD)>=0,"native seek");avcodec_flush_buffers(codec);}
        auto receive=[&]{int result;
            while((result=avcodec_receive_frame(codec,frame))>=0){
                double pts=frame->pts*timebase;
                for(int i=0;i<frame->nb_samples;++i){double position=pts+double(i)/48000;if(position+1e-9<seek||position>=duration-1e-9)continue;require(pcm.size()<48000*8*2,"PCM test cap");for(int c=0;c<2;c++)pcm.push_back(reinterpret_cast<float*>(frame->extended_data[c])[i]);}
                av_frame_unref(frame);
            }
            require(result==AVERROR(EAGAIN)||result==AVERROR_EOF,"receive frame");
        };
        int result;
        while((result=av_read_frame(format,packet))>=0){if(packet->stream_index==stream){require(avcodec_send_packet(codec,packet)>=0,"send packet");receive();}av_packet_unref(packet);}
        require(result==AVERROR_EOF,"read packet");require(avcodec_send_packet(codec,nullptr)>=0,"flush");receive();
        if(native)mt_snapshot(source.handle,out);
    }catch(...){av_packet_free(&packet);av_frame_free(&frame);avcodec_free_context(&codec);avformat_close_input(&format);if(io){av_freep(&io->buffer);avio_context_free(&io);}throw;}
    av_packet_free(&packet);av_frame_free(&frame);avcodec_free_context(&codec);avformat_close_input(&format);if(io){av_freep(&io->buffer);avio_context_free(&io);}return pcm;
}
int main(int argc,char**argv){try{
    require(argc==3,"base and fixture directory");av_log_set_level(AV_LOG_ERROR);
    for(const char*name:{"tone-a.m4a","tone-b.webm"}){
        std::string local=std::string(argv[2])+"/"+name,url=std::string(argv[1])+"/"+name;MTStats fullStats{},seekStats{};
        auto reference=decode(local.c_str(),false,0,nullptr),streamed=decode(url.c_str(),true,0,&fullStats);
        require(reference.size()==192000*2&&reference==streamed,"native AVIO differs from full local decode");
        auto seekReference=decode(local.c_str(),false,1.5,nullptr),sought=decode(url.c_str(),true,1.5,&seekStats);
        require(seekReference==sought&&sought.size()>=120000*2,"native AVIO seek differs from local seek");
        require(fullStats.buffer_high_bytes<=4096&&seekStats.buffer_high_bytes<=4096&&fullStats.resident_high_bytes<=128ull*1024*1024,"AVIO resource cap");
        printf("{\"case\":\"native_avio\",\"fixture\":\"%s\",\"full_frames\":%zu,\"seek_frames\":%zu,\"bit_equal_to_local_decode\":true,\"full_requests\":%u,\"seek_requests\":%u,\"media_cache_high_bytes\":%llu,\"observed_rss_high\":%llu}\n",name,streamed.size()/2,sought.size()/2,fullStats.requests,seekStats.requests,fullStats.buffer_high_bytes,std::max(fullStats.resident_high_bytes,seekStats.resident_high_bytes));
    }
    return 0;
}catch(const std::exception&e){fprintf(stderr,"FAIL %s\n",e.what());return 1;}}
