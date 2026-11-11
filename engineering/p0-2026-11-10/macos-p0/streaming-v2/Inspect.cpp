// MIT. Read-only same-version timeline diagnostic; no output device.
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/intreadwrite.h>
}
#include <cstdio>
int main(int argc,char**argv){
 if(argc!=2)return 64;av_log_set_level(AV_LOG_QUIET);AVFormatContext*f=nullptr;
 if(avformat_open_input(&f,argv[1],nullptr,nullptr)<0||avformat_find_stream_info(f,nullptr)<0)return 1;
 int index=av_find_best_stream(f,AVMEDIA_TYPE_AUDIO,-1,-1,nullptr,0);if(index<0)return 1;AVStream*s=f->streams[index];
 auto*c=avcodec_alloc_context3(avcodec_find_decoder(s->codecpar->codec_id));avcodec_parameters_to_context(c,s->codecpar);c->pkt_timebase=s->time_base;avcodec_open2(c,c->codec,nullptr);
 std::printf("{\"gate\":\"timeline_header\",\"stream_start_ticks\":%lld,\"timebase_num\":%d,\"timebase_den\":%d,\"stream_duration_ticks\":%lld,\"format_start_microseconds\":%lld,\"initial_padding\":%d,\"seek_preroll\":%d,\"trailing_padding\":%d}\n",s->start_time,s->time_base.num,s->time_base.den,s->duration,f->start_time,s->codecpar->initial_padding,s->codecpar->seek_preroll,s->codecpar->trailing_padding);
 AVPacket*p=av_packet_alloc();AVFrame*frame=av_frame_alloc();
 for(int count=0;count<2&&av_read_frame(f,p)>=0;){if(p->stream_index==index){size_t n=0;auto*skip=av_packet_get_side_data(p,AV_PKT_DATA_SKIP_SAMPLES,&n);
  std::printf("{\"gate\":\"packet\",\"pts\":%lld,\"duration\":%lld,\"skip_samples\":%u,\"discard_samples\":%u}\n",p->pts,p->duration,skip&&n>=10?AV_RL32(skip):0,skip&&n>=10?AV_RL32(skip+4):0);
  avcodec_send_packet(c,p);while(avcodec_receive_frame(c,frame)>=0){std::printf("{\"gate\":\"frame\",\"pts\":%lld,\"samples\":%d}\n",frame->pts,frame->nb_samples);av_frame_unref(frame);}count++;}av_packet_unref(p);}
 av_frame_free(&frame);av_packet_free(&p);avcodec_free_context(&c);avformat_close_input(&f);return 0;
}
