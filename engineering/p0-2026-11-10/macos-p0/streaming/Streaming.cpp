// MIT. Independent P0 streaming sink. Ring/mix design derives from the unchanged
// original MIT audio/probe.cpp; native AVIO derives from MIT DecodeProbe.cpp.
#define MA_NO_RUNTIME_LINKING
#define MA_ENABLE_ONLY_SPECIFIC_BACKENDS
#define MA_ENABLE_COREAUDIO
#define MA_NO_DECODING
#define MA_NO_ENCODING
#define MA_NO_ENGINE
#define MA_NO_RESOURCE_MANAGER
#define MA_NO_NODE_GRAPH
#include "miniaudio.h"
#include "stream_source.h"
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libswresample/swresample.h>
}
#include <mach/mach.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <thread>

namespace {
constexpr uint64_t rate=48000, capacity=32768, window=262144;
static_assert(std::atomic<uint64_t>::is_always_lock_free,"real-time counters");
void pause_ms(int n){std::this_thread::sleep_for(std::chrono::milliseconds(n));}
void require(bool x,const char *why){if(!x)throw std::runtime_error(why);}
uint64_t rss(){mach_task_basic_info_data_t i;mach_msg_type_number_t n=MACH_TASK_BASIC_INFO_COUNT;return task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&i,&n)==KERN_SUCCESS?i.resident_size:UINT64_MAX;}
struct Ring {
    std::array<float,capacity*2> pcm{};std::atomic<uint64_t> write{0},read{0},high{0};
    uint64_t size()const{return write.load(std::memory_order_acquire)-read.load(std::memory_order_acquire);}
    size_t push(const float *data,size_t frames){auto w=write.load();auto r=read.load(std::memory_order_acquire);frames=std::min(frames,size_t(capacity-(w-r)));
        for(size_t i=0;i<frames;i++){pcm[((w+i)%capacity)*2]=data[i*2];pcm[((w+i)%capacity)*2+1]=data[i*2+1];}
        write.store(w+frames,std::memory_order_release);auto previous=high.load();while(w+frames-r>previous&&!high.compare_exchange_weak(previous,w+frames-r)){}return frames;}
    bool pop(float *out){auto r=read.load();auto w=write.load(std::memory_order_acquire);if(r==w)return false;out[0]=pcm[(r%capacity)*2];out[1]=pcm[(r%capacity)*2+1];read.store(r+1,std::memory_order_release);return true;}
    uint64_t discard(){auto r=read.load(),w=write.load(std::memory_order_acquire);read.store(w,std::memory_order_release);return w-r;}
};
struct Session;
struct Decoder {
    Session *owner;Ring ring;MTHandle *handle=nullptr;uint64_t total=0,descriptorNS=0,position=0;
    std::thread worker;std::atomic<bool> cancel{false},done{false},inflight{false};std::atomic<int> error{0},transportStatus{0};
    std::atomic<uint64_t> produced{0},consumed{0},network{0},unique{0},requests{0},bufferHigh{0},firstBytes{0},firstPCM{0},pcmNetwork{0},firstCallback{0},callbackNetworkUpper{0},contentFrames{0},readEpoch{0};
    std::atomic<uint64_t> seekRequest{0},seekAck{0},seekDone{0},discarded{0};std::atomic<double> seekTarget{0},seekFirstPTS{-1};
    std::atomic<uint64_t> sourceRate{0},sourceChannels{0};
    explicit Decoder(Session *s):owner(s){}
    bool stopping()const;
    static int interrupt(void *p){return static_cast<Decoder*>(p)->stopping();}
    static int read(void *p,uint8_t *buffer,int size){auto &d=*static_cast<Decoder*>(p);if(d.stopping())return AVERROR_EXIT;
        size_t got=0;d.readEpoch.fetch_add(1,std::memory_order_release);d.inflight=true;MTStatus status=mt_read_at(d.handle,d.position,buffer,size,&got);MTStats s{};mt_snapshot(d.handle,&s);
        d.network=s.network_bytes;d.unique=s.unique_validated_bytes;d.requests=s.requests;d.bufferHigh=s.buffer_high_bytes;d.transportStatus=status;d.inflight=false;d.readEpoch.fetch_add(1,std::memory_order_release);
        if(status==MT_EOF)return AVERROR_EOF;if(status==MT_CANCELLED)return AVERROR_EXIT;if(status!=MT_OK)return AVERROR(EIO);
        uint64_t zero=0;d.firstBytes.compare_exchange_strong(zero,sp_now_ns());d.position+=got;return int(got);}
    static int64_t seek(void *p,int64_t offset,int origin){auto &d=*static_cast<Decoder*>(p);if(origin==AVSEEK_SIZE)return d.total;
        origin&=~AVSEEK_FORCE;int64_t base=origin==SEEK_SET?0:origin==SEEK_CUR?int64_t(d.position):origin==SEEK_END?int64_t(d.total):-1;
        if(base<0 || offset<-base || offset>int64_t(d.total)-base)return AVERROR(EINVAL);d.position=uint64_t(base+offset);return int64_t(d.position);}
    void decode(double initialSeek);
    void launch(double target){worker=std::thread([this,target]{decode(target);done=true;});}
    void render(float *out,uint64_t now){
        auto requested=seekRequest.load(std::memory_order_acquire);
        if(requested>seekAck.load()){discarded.fetch_add(ring.discard());seekAck.store(requested,std::memory_order_release);}
        if(ring.pop(out)){consumed++;uint64_t zero=0;if(firstCallback.compare_exchange_strong(zero,now)){
                // Bounded, nonspinning sequence sample: a racing observation
                // conservatively forfeits the early-submission proof.
                auto before=readEpoch.load(std::memory_order_acquire),observed=network.load(),after=readEpoch.load(std::memory_order_acquire);
                callbackNetworkUpper=before!=after?total:observed+((after&1)?window:0);
            }
            if(std::abs(out[0])>1e-8f||std::abs(out[1])>1e-8f)contentFrames++;}
    }
};
struct Session {
    Decoder first{this},next{this};std::atomic<bool> cancelled{false};std::atomic<int> reason{0};std::atomic<uint64_t> peakRSS{0};
    uint64_t actionNS,deadlineNS;std::thread watchdog;std::mutex handles,deviceLock;
    ma_context context{};ma_device device{};bool contextReady=false,deviceReady=false;std::atomic<bool> nextAttached{false};
    std::atomic<uint64_t> clock{0},callbacks{0},underflows{0},transitionStart{UINT64_MAX-rate*10},transitionLength{0},transitions{0},starts{0},stops{0},firstSubmission{0},preMuteNonzero{0},clipped{0};
    explicit Session(uint64_t start):actionNS(start),deadlineNS(start+90ull*1000000000){watchdog=std::thread([this]{
        while(!cancelled){uint64_t used=rss(),previous=peakRSS.load();while(used>previous&&!peakRSS.compare_exchange_weak(previous,used)){}
            if(used>256ull*1024*1024){requestCancel(2);break;}if(sp_now_ns()>=deadlineNS){requestCancel(3);break;}pause_ms(100);}});}
    void requestCancel(int why=1){int zero=0;reason.compare_exchange_strong(zero,why);cancelled=true;
        {std::lock_guard<std::mutex> hold(handles);for(auto *d:{&first,&next})if(d->handle){d->cancel=true;mt_cancel(d->handle);}}
        sp_cancel_resolver();std::lock_guard<std::mutex> hold(deviceLock);if(deviceReady)ma_device_stop(&device);
    }
    void attach(Decoder &d,SPSource source){require(source.handle && source.error==0 && source.total_bytes>0 && source.total_bytes<=16ull*1024*1024,"descriptor");
        std::lock_guard<std::mutex> hold(handles);if(cancelled){mt_cancel(source.handle);mt_destroy(source.handle);throw std::runtime_error("cancelled before attach");}
        require(!d.handle,"duplicate input");d.handle=source.handle;d.total=source.total_bytes;d.descriptorNS=source.descriptor_ns;
    }
    void prepare(Decoder &d){uint64_t deadline=sp_now_ns()+8ull*1000000000;while(d.ring.size()<8192&&!d.done&&!cancelled){require(sp_now_ns()<deadline,"prefill timeout");pause_ms(1);}
        require(!cancelled&&d.error==0&&d.ring.size()>=8192,"prefill failed");}
    static void callback(ma_device *device,void *out,const void*,ma_uint32 frames){auto &s=*static_cast<Session*>(device->pUserData);auto *output=static_cast<float*>(out);
        uint64_t now=sp_now_ns(),zero=0;s.firstSubmission.compare_exchange_strong(zero,now);auto begin=s.clock.load();auto cross=s.transitionStart.load(std::memory_order_acquire);auto length=s.transitionLength.load();
        for(size_t i=0;i<frames;i++){float a[2]{},b[2]{};auto t=begin+i;bool needA=t<cross+length,needB=t>=cross;
            if(needA){auto consumed=s.first.consumed.load();s.first.render(a,now);if(consumed==s.first.consumed.load()&&!s.first.done)s.underflows++;}
            if(needB){auto consumed=s.next.consumed.load();s.next.render(b,now);if(consumed==s.next.consumed.load()&&!s.next.done)s.underflows++;}
            // Consume/mix real PCM but always submit silence in this proof.
            double phase=length?std::clamp(double(t)-double(cross),0.0,double(length))/length:double(needB);
            float gainA=float(std::cos(phase*1.5707963267948966)),gainB=float(std::sin(phase*1.5707963267948966));
            bool nonzero=false;for(int c=0;c<2;c++){float value=a[c]*gainA+b[c]*gainB;if(std::abs(value)>1)s.clipped++;if(std::abs(value)>1e-8f)nonzero=true;output[i*2+c]=0;}if(nonzero)s.preMuteNonzero++;
            if(t==cross+length)s.transitions++;}
        s.clock=begin+frames;s.callbacks++;
    }
    static void notification(const ma_device_notification *n){auto &s=*static_cast<Session*>(n->pDevice->pUserData);if(n->type==ma_device_notification_type_started)s.starts++;if(n->type==ma_device_notification_type_stopped)s.stops++;}
    void startOutput(){std::lock_guard<std::mutex> hold(deviceLock);require(!cancelled&&!deviceReady,"start state");auto cc=ma_context_config_init();
        cc.coreaudio.sessionCategory=ma_ios_session_category_none;cc.coreaudio.noAudioSessionActivate=MA_TRUE;cc.coreaudio.noAudioSessionDeactivate=MA_TRUE;
        ma_backend backend=ma_backend_coreaudio;require(ma_context_init(&backend,1,&cc,&context)==MA_SUCCESS,"context");contextReady=true;
        auto config=ma_device_config_init(ma_device_type_playback);config.playback.format=ma_format_f32;config.playback.channels=2;config.playback.shareMode=ma_share_mode_shared;config.sampleRate=rate;config.periodSizeInFrames=256;
        config.dataCallback=callback;config.notificationCallback=notification;config.pUserData=this;require(ma_device_init(&context,&config,&device)==MA_SUCCESS,"device");deviceReady=true;require(ma_device_start(&device)==MA_SUCCESS,"device start");}
    void prepareNext(SPSource source){require(!nextAttached.exchange(true),"one next only");attach(next,source);next.launch(0);prepare(next);
        transitionLength=rate/4;transitionStart.store(clock.load()+rate/4,std::memory_order_release);}
    void seekFirst(double seconds){require(deviceReady&&!nextAttached&&seconds>=0&&seconds<=900&&!first.done,"seek state");first.seekTarget=seconds;
        auto generation=first.seekRequest.fetch_add(1,std::memory_order_release)+1;uint64_t end=sp_now_ns()+8ull*1000000000;
        while(first.seekDone.load()<generation&&!first.done&&!cancelled){require(sp_now_ns()<end,"seek timeout");pause_ms(1);}require(first.seekDone>=generation&&first.error==0,"seek failed");}
    void report(const char *name){
        std::printf("{\"gate\":\"stream_session\",\"case\":\"%s\",\"action_ns\":%llu,\"first_output_callback_ns\":%llu,\"clock_frames\":%llu,\"callbacks\":%llu,\"underflow_frames\":%llu,\"transitions\":%llu,\"pcm_pool_bytes\":%zu,\"network_total_bytes\":%llu,\"rss_peak_bytes\":%llu,\"reason\":%d,\"audible\":false,\"submitted_nonzero_frames\":0,\"speaker_first_sound_measured\":false}\n",name,actionNS,firstSubmission.load(),clock.load(),callbacks.load(),underflows.load(),transitions.load(),sizeof(first.ring.pcm)+sizeof(next.ring.pcm),first.network.load()+next.network.load(),peakRSS.load(),reason.load());
        for(auto *d:{&first,&next})if(d->handle)std::printf("{\"gate\":\"stream_input\",\"slot\":%d,\"descriptor_ns\":%llu,\"first_validated_bytes_ns\":%llu,\"first_decoded_pcm_ns\":%llu,\"first_callback_consumption_ns\":%llu,\"first_pcm_network_bytes\":%llu,\"first_callback_network_upper_bytes\":%llu,\"total_bytes\":%llu,\"network_bytes\":%llu,\"unique_bytes\":%llu,\"requests\":%llu,\"buffer_high_bytes\":%llu,\"pcm_high_frames\":%llu,\"decoded_frames\":%llu,\"consumed_frames\":%llu,\"rendered_nonzero_content_frames\":%llu,\"sample_rate\":%llu,\"channels\":%llu,\"seek_generation\":%llu,\"seek_first_pts\":%.8f,\"discarded_seek_pcm_frames\":%llu,\"decoder_error\":%d,\"transport_status\":%d}\n",d==&first?0:1,d->descriptorNS,d->firstBytes.load(),d->firstPCM.load(),d->firstCallback.load(),d->pcmNetwork.load(),d->callbackNetworkUpper.load(),d->total,d->network.load(),d->unique.load(),d->requests.load(),d->bufferHigh.load(),d->ring.high.load(),d->produced.load(),d->consumed.load(),d->contentFrames.load(),d->sourceRate.load(),d->sourceChannels.load(),d->seekDone.load(),d->seekFirstPTS.load(),d->discarded.load(),d->error.load(),d->transportStatus.load());
        std::fflush(stdout);
    }
    ~Session(){requestCancel();if(watchdog.joinable())watchdog.join();
        {std::lock_guard<std::mutex> hold(deviceLock);if(deviceReady){ma_device_uninit(&device);deviceReady=false;}if(contextReady)ma_context_uninit(&context);}
        unsigned destroyed=0,joined=0;for(auto *d:{&first,&next}){if(d->worker.joinable()){d->worker.join();joined++;}if(d->handle){MTStats stats{};mt_snapshot(d->handle,&stats);d->network=stats.network_bytes;mt_destroy(d->handle);d->handle=nullptr;destroyed++;}}
        std::printf("{\"gate\":\"stream_cleanup\",\"handles_destroyed\":%u,\"decoder_threads_joined_here\":%u,\"output_starts\":%llu,\"output_stops\":%llu,\"premute_nonzero_mix_frames\":%llu,\"clipped_samples\":%llu,\"network_total_bytes\":%llu,\"outcome\":\"pass\"}\n",destroyed,joined,starts.load(),stops.load(),preMuteNonzero.load(),clipped.load(),first.network.load()+next.network.load());
    }
};
bool Decoder::stopping()const{return cancel.load()||owner->cancelled.load();}
void Decoder::decode(double initialSeek){
    AVFormatContext *format=avformat_alloc_context();AVIOContext *io=nullptr;AVCodecContext *codec=nullptr;SwrContext *swr=nullptr;AVFrame *frame=av_frame_alloc();AVPacket *packet=av_packet_alloc();int stream=-1;
    try{
        auto ok=[](int code){if(code<0)throw code;};require(format&&frame&&packet,"decoder allocation");
        format->probesize=65536;format->max_analyze_duration=AV_TIME_BASE;format->max_streams=4;format->interrupt_callback={interrupt,this};
        io=avio_alloc_context(static_cast<uint8_t*>(av_malloc(4096)),4096,0,this,read,nullptr,seek);require(io,"AVIO allocation");io->seekable=AVIO_SEEKABLE_NORMAL;format->pb=io;format->flags|=AVFMT_FLAG_CUSTOM_IO;
        ok(avformat_open_input(&format,nullptr,nullptr,nullptr));ok(avformat_find_stream_info(format,nullptr));stream=av_find_best_stream(format,AVMEDIA_TYPE_AUDIO,-1,-1,nullptr,0);ok(stream);
        auto *parameters=format->streams[stream]->codecpar;require(parameters->codec_id==AV_CODEC_ID_AAC||parameters->codec_id==AV_CODEC_ID_OPUS,"codec scope");
        codec=avcodec_alloc_context3(avcodec_find_decoder(parameters->codec_id));require(codec,"codec allocation");ok(avcodec_parameters_to_context(codec,parameters));codec->pkt_timebase=format->streams[stream]->time_base;codec->thread_count=1;ok(avcodec_open2(codec,codec->codec,nullptr));
        require(codec->sample_rate>=8000&&codec->sample_rate<=192000&&codec->ch_layout.nb_channels>=1&&codec->ch_layout.nb_channels<=8,"format bounds");sourceRate=codec->sample_rate;sourceChannels=codec->ch_layout.nb_channels;
        AVChannelLayout stereo=AV_CHANNEL_LAYOUT_STEREO;ok(swr_alloc_set_opts2(&swr,&stereo,AV_SAMPLE_FMT_FLT,rate,&codec->ch_layout,codec->sample_fmt,codec->sample_rate,0,nullptr));ok(swr_init(swr));
        double timebase=av_q2d(format->streams[stream]->time_base),target=initialSeek,nextPTS=0;
        double duration=format->streams[stream]->duration==AV_NOPTS_VALUE?INFINITY:format->streams[stream]->duration*timebase;
        uint64_t currentSeek=0;std::array<float,8192*2> pcm{};
        auto performSeek=[&](double seconds){auto at=int64_t(std::max(0.0,seconds-.12)/timebase);ok(avformat_seek_file(format,stream,INT64_MIN,at,at,AVSEEK_FLAG_BACKWARD));avcodec_flush_buffers(codec);swr_close(swr);ok(swr_init(swr));nextPTS=seconds;target=seconds;seekFirstPTS=-1;};
        if(target>0)performSeek(target);
        auto receive=[&]{int code;
            while(!stopping() && seekRequest.load()==currentSeek && (code=avcodec_receive_frame(codec,frame))>=0){
                require(swr_get_out_samples(swr,frame->nb_samples)<=8192,"converted block bound");double pts=frame->pts==AV_NOPTS_VALUE?nextPTS:frame->pts*timebase-double(swr_get_delay(swr,codec->sample_rate))/codec->sample_rate;
                uint8_t *output=reinterpret_cast<uint8_t*>(pcm.data());int count=swr_convert(swr,&output,8192,const_cast<const uint8_t**>(frame->extended_data),frame->nb_samples);ok(count);for(int i=0;i<count*2;i++)require(std::isfinite(pcm[i]),"finite PCM");nextPTS=pts+double(count)/rate;
                size_t begin=size_t(std::min(double(count),std::max(0.0,std::ceil((target-pts)*rate-.01))));size_t end=size_t(std::max(0.0,std::min(double(count),std::ceil((duration-pts)*rate-.01))));
                if(begin<end){uint64_t zero=0;if(firstPCM.compare_exchange_strong(zero,sp_now_ns()))pcmNetwork=network.load();if(seekFirstPTS<0)seekFirstPTS=pts+double(begin)/rate;
                    while(begin<end&&!stopping()&&seekRequest.load()==currentSeek){size_t n=ring.push(pcm.data()+begin*2,end-begin);begin+=n;produced+=n;require(produced<=rate*900,"output bound");if(!n)pause_ms(1);}
                    if(currentSeek && ring.size()>=8192)seekDone=currentSeek;}
                av_frame_unref(frame);
            }
            if(!stopping()&&seekRequest.load()==currentSeek&&code<0&&code!=AVERROR(EAGAIN)&&code!=AVERROR_EOF)throw code;
        };
        while(!stopping()){
            if(seekRequest.load()!=currentSeek){auto requested=seekRequest.load();while(seekAck.load()<requested&&!stopping())pause_ms(1);if(stopping())break;performSeek(seekTarget.load());currentSeek=requested;}
            int code=av_read_frame(format,packet);if(code==AVERROR_EOF){ok(avcodec_send_packet(codec,nullptr));receive();break;}ok(code);
            if(packet->stream_index==stream){ok(avcodec_send_packet(codec,packet));receive();}av_packet_unref(packet);
        }
    }catch(int code){if(!stopping())error=code;}catch(...){if(!stopping())error=AVERROR_UNKNOWN;}
    av_frame_free(&frame);av_packet_free(&packet);swr_free(&swr);avcodec_free_context(&codec);avformat_close_input(&format);if(io){av_freep(&io->buffer);avio_context_free(&io);}
}
void verifyEarly(Decoder &d){require(d.firstPCM>0&&d.firstCallback>0,"PCM and callback observed");require(d.pcmNetwork<d.total&&d.callbackNetworkUpper<d.total,"whole media fetched before render");require(d.bufferHigh<=window&&d.ring.high<=capacity,"bounded buffers");require(d.error==0,"decoder healthy");}
}
int main(int argc,char **argv){
    av_log_set_level(AV_LOG_QUIET);uint64_t action=sp_now_ns();
    try{
        require(argc>=3,"arguments");Session session(action);bool live=strcmp(argv[1],"public")==0;require(live||argc>=5,"local arguments");
        const char *mode=live?"public":argv[2];SPSource first=live?sp_resolve(argv[2],0,"aac"):sp_local(argv[3],std::strtoull(argv[4],nullptr,10));
        session.attach(session.first,first);session.first.launch(0);
        if(!strcmp(mode,"cancel")){
            pause_ms(200);auto when=sp_now_ns();session.requestCancel();session.first.worker.join();session.report(mode);
            std::printf("{\"gate\":\"cancel_join\",\"elapsed_ms\":%.3f,\"outcome\":\"pass\"}\n",(sp_now_ns()-when)/1e6);return 0;
        }
        if(!strcmp(mode,"disconnect")||!strcmp(mode,"ignore")){
            bool failed=false;try{session.prepare(session.first);}catch(...){failed=true;}require(failed&&session.first.error!=0,"expected transport rejection");session.report(mode);return 0;
        }
        session.prepare(session.first);
        // Delay output briefly: a full ring must backpressure the decoder/network.
        pause_ms(150);auto bytes=session.first.network.load();pause_ms(150);require(bytes==session.first.network.load(),"prefill keeps fetching despite backpressure");
        session.startOutput();pause_ms(400);verifyEarly(session.first);
        if(!strcmp(mode,"seek")){session.seekFirst(30);pause_ms(400);require(session.first.seekDone==1&&std::abs(session.first.seekFirstPTS.load()-30)<.002,"seek target");}
        else if(live||!strcmp(mode,"late")){
            require(session.next.produced==0&&!session.next.handle,"next prepared early");pause_ms(live?1600:200);
            SPSource next=live?sp_resolve(argv[2],1,"aac"):sp_local(argv[5],std::strtoull(argv[6],nullptr,10));
            session.prepareNext(next);pause_ms(1000);auto consumed=session.first.consumed.load(),nextConsumed=session.next.consumed.load();pause_ms(400);
            require(session.transitions==1&&session.first.consumed==consumed&&session.next.consumed>nextConsumed,"post-transition ownership");verifyEarly(session.next);
        }
        if(strcmp(mode,"seek"))require(session.underflows==0,"stream underrun");
        require(session.first.network+session.next.network<=32ull*1024*1024,"aggregate network cap");session.report(mode);
        std::puts("{\"gate\":\"streaming_proof\",\"outcome\":\"pass\",\"media_file_written\":false,\"human_audibility\":false}");return 0;
    }catch(const std::exception &error){std::fprintf(stderr,"stream proof failed: %s\n",error.what());return 1;}
}
