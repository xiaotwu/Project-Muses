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
#include <CommonCrypto/CommonDigest.h>
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
#include <string>
#include <thread>

namespace {
constexpr uint64_t rate=48000, capacity=32768, window=262144;
enum Phase { Opening, Decoding, CodecDrain, SwrDrain, Ended, Failed, Cancelled };
const char *phaseName(int p){static const char *names[]={"opening","decoding","codec_drain","swr_drain","ended","failed","cancelled"};return names[p];}
const char *reasonName(int p){switch(p){case 0:return "running";case 1:return "explicit_cancel";case 2:return "rss_limit";case 3:return "deadline";case 4:return "input_failed";case 5:return "normal_eof";case 6:return "bounded_probe_complete";default:return "controller_failure";}}
static_assert(std::atomic<uint64_t>::is_always_lock_free,"real-time counters");
void pause_ms(int n){std::this_thread::sleep_for(std::chrono::milliseconds(n));}
void require(bool x,const char *why){if(!x)throw std::runtime_error(why);}
uint64_t rss(){mach_task_basic_info_data_t i;mach_msg_type_number_t n=MACH_TASK_BASIC_INFO_COUNT;return task_info(mach_task_self(),MACH_TASK_BASIC_INFO,(task_info_t)&i,&n)==KERN_SUCCESS?i.resident_size:UINT64_MAX;}
struct Digest {
    CC_SHA256_CTX context{};std::array<float,512> tail{};uint64_t frames=0;long double energy=0;
    Digest(){CC_SHA256_Init(&context);}
    void add(const float *pcm,size_t count){CC_SHA256_Update(&context,pcm,CC_LONG(count*2*sizeof(float)));for(size_t i=0;i<count;i++){for(int c=0;c<2;c++){float v=pcm[i*2+c];tail[(frames%256)*2+c]=v;energy+=double(v)*v;}frames++;}}
    static std::string hex(CC_SHA256_CTX value){unsigned char bytes[32];CC_SHA256_Final(bytes,&value);char out[65]{};for(int i=0;i<32;i++)snprintf(out+i*2,3,"%02x",bytes[i]);return out;}
    std::string full()const{return hex(context);}
    std::string last()const{CC_SHA256_CTX value;CC_SHA256_Init(&value);uint64_t count=std::min(frames,uint64_t(256)),start=frames-count;for(uint64_t i=start;i<frames;i++)CC_SHA256_Update(&value,tail.data()+(i%256)*2,2*sizeof(float));return hex(value);}
};
struct Ring {
    std::array<float,capacity*2> pcm{};std::atomic<uint64_t> write{0},read{0},high{0};
    // Deterministic local regression hook: pause AFTER data copy, BEFORE publish.
    // Never enabled for a public run; cancellation always releases it.
    std::atomic<bool> holdNextPublish{false},publishHeld{false},releasePublish{false};
    uint64_t size()const{return write.load(std::memory_order_acquire)-read.load(std::memory_order_acquire);}
    size_t push(const float *data,size_t frames){auto w=write.load();auto r=read.load(std::memory_order_acquire);frames=std::min(frames,size_t(capacity-(w-r)));
        for(size_t i=0;i<frames;i++){pcm[((w+i)%capacity)*2]=data[i*2];pcm[((w+i)%capacity)*2+1]=data[i*2+1];}
        if(frames&&holdNextPublish.exchange(false)){publishHeld=true;while(!releasePublish)pause_ms(1);publishHeld=false;}
        write.store(w+frames,std::memory_order_release);auto previous=high.load();while(w+frames-r>previous&&!high.compare_exchange_weak(previous,w+frames-r)){}return frames;}
    bool pop(float *out){auto r=read.load();auto w=write.load(std::memory_order_acquire);if(r==w)return false;out[0]=pcm[(r%capacity)*2];out[1]=pcm[(r%capacity)*2+1];read.store(r+1,std::memory_order_release);return true;}
    uint64_t discard(){auto r=read.load(),w=write.load(std::memory_order_acquire);read.store(w,std::memory_order_release);return w-r;}
};
struct Session;
struct Decoder {
    Session *owner;Ring ring;MTHandle *handle=nullptr;uint64_t total=0,descriptorNS=0,position=0;
    std::thread worker;std::atomic<bool> cancel{false},done{false},inflight{false};std::atomic<int> error{0},transportStatus{0};
    std::atomic<int> firstNonCancelTransportFailure{0};
    std::atomic<bool> holdFailureReturn{false},failureReturnHeld{false},releaseFailureReturn{false};
    std::mutex control;std::atomic<int> phase{Opening};std::atomic<double> presentationOrigin{0};Digest producedDigest,consumedDigest,seekProducedDigest,seekConsumedDigest;
    std::atomic<uint64_t> sealedWrite{UINT64_MAX};
    std::atomic<uint64_t> codecDrainFrames{0},swrDrainFrames{0},codecDrainNS{0},swrDrainNS{0},producerEndNS{0},ringDrainNS{0};
    std::atomic<uint64_t> produced{0},consumed{0},network{0},unique{0},requests{0},bufferHigh{0},firstBytes{0},firstPCM{0},pcmNetwork{0},firstCallback{0},callbackNetworkUpper{0},contentFrames{0},readEpoch{0};
    std::atomic<uint64_t> seekRequest{0},seekQuiesced{0},seekAck{0},seekDone{0},discarded{0};std::atomic<double> seekTarget{0},seekFirstPTS{-1};
    std::atomic<uint64_t> sourceRate{0},sourceChannels{0},codecID{0};
    std::atomic<uint64_t> seekCodecResets{0},seekTrimmedFrames{0};std::atomic<double> seekFirstPacketPTS{-1};
    explicit Decoder(Session *s):owner(s){}
    bool stopping()const;
    static int interrupt(void *p){return static_cast<Decoder*>(p)->stopping();}
    static int read(void *p,uint8_t *buffer,int size){auto &d=*static_cast<Decoder*>(p);if(d.stopping())return AVERROR_EXIT;
        size_t got=0;d.readEpoch.fetch_add(1,std::memory_order_release);d.inflight=true;MTStatus status=mt_read_at(d.handle,d.position,buffer,size,&got);
        if(status<0&&status!=MT_CANCELLED){int zero=0;d.firstNonCancelTransportFailure.compare_exchange_strong(zero,status);
            if(d.holdFailureReturn){d.failureReturnHeld=true;while(!d.releaseFailureReturn)pause_ms(1);}}
        MTStats s{};mt_snapshot(d.handle,&s);
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
        if(requested>seekAck.load()){
            // Producer has completed its last old-generation publish first.
            if(seekQuiesced.load(std::memory_order_acquire)>=requested){discarded.fetch_add(ring.discard());seekAck.store(requested,std::memory_order_release);}
            return;
        }
        bool available=ring.pop(out);
        if(!available&&phase.load(std::memory_order_acquire)==Ended){
            // Ended publishes the final write index. A failed pop BEFORE that
            // acquire observation cannot prove the sealed ring is empty.
            available=ring.pop(out);
            if(!available&&ring.read.load(std::memory_order_acquire)==sealedWrite.load()){uint64_t zero=0;ringDrainNS.compare_exchange_strong(zero,now);}
        }
        if(available){consumed++;uint64_t zero=0;if(firstCallback.compare_exchange_strong(zero,now)){
                // Bounded, nonspinning sequence sample: a racing observation
                // conservatively forfeits the early-submission proof.
                auto before=readEpoch.load(std::memory_order_acquire),observed=network.load(),after=readEpoch.load(std::memory_order_acquire);
                callbackNetworkUpper=before!=after?total:observed+((after&1)?window:0);
            }
            consumedDigest.add(out,1);if(seekAck>0)seekConsumedDigest.add(out,1);if(std::abs(out[0])>1e-8f||std::abs(out[1])>1e-8f)contentFrames++;
        }
    }
};
struct Session {
    Decoder first{this},next{this};std::atomic<bool> cancelled{false};std::atomic<int> reason{0};std::atomic<uint64_t> peakRSS{0};
    uint64_t actionNS,deadlineNS;std::thread watchdog;std::mutex handles,deviceLock;
    ma_context context{};ma_device device{};bool contextReady=false,deviceReady=false;std::atomic<bool> nextAttached{false};
    bool joined=false;unsigned joinedWorkers=0;
    std::atomic<uint64_t> clock{0},callbacks{0},underflows{0},transitionStart{UINT64_MAX-rate*10},transitionLength{0},transitions{0},starts{0},stops{0},firstSubmission{0},preMuteNonzero{0},clipped{0};
    explicit Session(uint64_t start):actionNS(start),deadlineNS(start+90ull*1000000000){watchdog=std::thread([this]{
        while(!cancelled){uint64_t used=rss(),previous=peakRSS.load();while(used>previous&&!peakRSS.compare_exchange_weak(previous,used)){}
            if(first.error||next.error){requestCancel(4);break;}if(used>256ull*1024*1024){requestCancel(2);break;}if(sp_now_ns()>=deadlineNS){requestCancel(3);break;}pause_ms(100);}});}
    void requestCancel(int why=1){int zero=0;reason.compare_exchange_strong(zero,why);cancelled=true;
        {std::lock_guard<std::mutex> hold(handles);for(auto *d:{&first,&next})if(d->handle){d->cancel=true;d->ring.releasePublish=true;d->releaseFailureReturn=true;mt_cancel(d->handle);}}
        sp_cancel_resolver();std::lock_guard<std::mutex> hold(deviceLock);if(deviceReady)ma_device_stop(&device);
    }
    void attach(Decoder &d,SPSource source){require(source.handle && source.error==0 && source.total_bytes>0 && source.total_bytes<=16ull*1024*1024,"descriptor");
        std::lock_guard<std::mutex> hold(handles);if(cancelled){mt_cancel(source.handle);mt_destroy(source.handle);throw std::runtime_error("cancelled before attach");}
        require(!d.handle,"duplicate input");d.handle=source.handle;d.total=source.total_bytes;d.descriptorNS=source.descriptor_ns;
    }
    void prepare(Decoder &d){uint64_t deadline=sp_now_ns()+8ull*1000000000;while(d.ring.size()<8192&&!d.done&&!cancelled){require(sp_now_ns()<deadline,"prefill timeout");pause_ms(1);}
        require(!cancelled&&d.error==0&&(d.ring.size()>=8192||(d.phase==Ended&&d.ring.size()>0)),"prefill failed");}
    static void callback(ma_device *device,void *out,const void*,ma_uint32 frames){auto &s=*static_cast<Session*>(device->pUserData);auto *output=static_cast<float*>(out);
        if(s.cancelled.load(std::memory_order_acquire)){std::fill(output,output+frames*2,0);return;}
        uint64_t now=sp_now_ns(),zero=0;s.firstSubmission.compare_exchange_strong(zero,now);auto begin=s.clock.load();auto cross=s.transitionStart.load(std::memory_order_acquire);auto length=s.transitionLength.load();
        for(size_t i=0;i<frames;i++){if(s.cancelled.load(std::memory_order_acquire)){std::fill(output+i*2,output+frames*2,0);break;}float a[2]{},b[2]{};auto t=begin+i;bool needA=t<cross+length,needB=t>=cross;
            if(needA){auto consumed=s.first.consumed.load();s.first.render(a,now);if(consumed==s.first.consumed.load()&&s.first.phase<Ended)s.underflows++;}
            if(needB){auto consumed=s.next.consumed.load();s.next.render(b,now);if(consumed==s.next.consumed.load()&&s.next.phase<Ended)s.underflows++;}
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
    uint64_t requestSeek(double seconds){require(deviceReady&&!nextAttached&&seconds>=0&&seconds<=900,"seek state");std::lock_guard<std::mutex> lock(first.control);
        if(first.phase!=Decoding||first.seekRequest!=0)return 0;first.seekTarget=seconds;return first.seekRequest.fetch_add(1,std::memory_order_release)+1;}
    void waitSeek(uint64_t generation){require(generation>0,"seek rejected at terminal input");uint64_t end=sp_now_ns()+8ull*1000000000;
        while(first.seekDone.load()<generation&&!first.done&&!cancelled){require(sp_now_ns()<end,"seek timeout");pause_ms(1);}require(first.seekDone>=generation&&first.error==0,"seek failed");}
    void seekFirst(double seconds){waitSeek(requestSeek(seconds));}
    void finish(int why){if(joined)return;requestCancel(why);if(watchdog.joinable())watchdog.join();
        {std::lock_guard<std::mutex> hold(deviceLock);if(deviceReady){ma_device_uninit(&device);deviceReady=false;}if(contextReady){ma_context_uninit(&context);contextReady=false;}}
        for(auto *d:{&first,&next})if(d->worker.joinable()){d->worker.join();joinedWorkers++;}
        if(first.error||next.error||first.firstNonCancelTransportFailure||next.firstNonCancelTransportFailure)reason=4;joined=true;}
    void report(const char *name){
        std::printf("{\"gate\":\"stream_session\",\"case\":\"%s\",\"action_ns\":%llu,\"first_output_callback_ns\":%llu,\"clock_frames\":%llu,\"callbacks\":%llu,\"underflow_frames\":%llu,\"transitions\":%llu,\"pcm_pool_bytes\":%zu,\"network_total_bytes\":%llu,\"rss_peak_bytes\":%llu,\"reason\":%d,\"audible\":false,\"submitted_nonzero_frames\":0,\"speaker_first_sound_measured\":false}\n",name,actionNS,firstSubmission.load(),clock.load(),callbacks.load(),underflows.load(),transitions.load(),sizeof(first.ring.pcm)+sizeof(next.ring.pcm),first.network.load()+next.network.load(),peakRSS.load(),reason.load());
        for(auto *d:{&first,&next})if(d->handle)std::printf("{\"gate\":\"stream_input\",\"slot\":%d,\"descriptor_ns\":%llu,\"first_validated_bytes_ns\":%llu,\"first_decoded_pcm_ns\":%llu,\"first_callback_consumption_ns\":%llu,\"first_pcm_network_bytes\":%llu,\"first_callback_network_upper_bytes\":%llu,\"total_bytes\":%llu,\"network_bytes\":%llu,\"unique_bytes\":%llu,\"requests\":%llu,\"buffer_high_bytes\":%llu,\"pcm_high_frames\":%llu,\"decoded_frames\":%llu,\"consumed_frames\":%llu,\"rendered_nonzero_content_frames\":%llu,\"sample_rate\":%llu,\"channels\":%llu,\"seek_generation\":%llu,\"seek_first_pts\":%.8f,\"discarded_seek_pcm_frames\":%llu,\"decoder_error\":%d,\"transport_status\":%d}\n",d==&first?0:1,d->descriptorNS,d->firstBytes.load(),d->firstPCM.load(),d->firstCallback.load(),d->pcmNetwork.load(),d->callbackNetworkUpper.load(),d->total,d->network.load(),d->unique.load(),d->requests.load(),d->bufferHigh.load(),d->ring.high.load(),d->produced.load(),d->consumed.load(),d->contentFrames.load(),d->sourceRate.load(),d->sourceChannels.load(),d->seekDone.load(),d->seekFirstPTS.load(),d->discarded.load(),d->error.load(),d->transportStatus.load());
        std::fflush(stdout);
        std::printf("{\"gate\":\"stream_end\",\"reason\":\"%s\",\"input_failure\":%s,\"joined_workers\":%u}\n",reasonName(reason),first.error||next.error?"true":"false",joinedWorkers);
        for(auto *d:{&first,&next})if(d->handle)std::printf("{\"gate\":\"stream_drain\",\"slot\":%d,\"phase\":\"%s\",\"codec\":\"%s\",\"presentation_origin_seconds\":%.8f,\"sealed_write_frames\":%llu,\"ring_read_frames\":%llu,\"ring_remaining_frames\":%llu,\"codec_drain_ns\":%llu,\"swr_drain_ns\":%llu,\"producer_end_ns\":%llu,\"ring_drain_ns\":%llu,\"codec_drain_frames\":%llu,\"swr_drain_frames\":%llu,\"produced_frames\":%llu,\"consumed_frames\":%llu,\"produced_pcm_sha256\":\"%s\",\"consumed_pcm_sha256\":\"%s\",\"produced_tail_sha256\":\"%s\",\"consumed_tail_sha256\":\"%s\"}\n",d==&first?0:1,phaseName(d->phase),avcodec_get_name(AVCodecID(d->codecID.load())),d->presentationOrigin.load(),d->sealedWrite.load(),d->ring.read.load(),d->ring.size(),d->codecDrainNS.load(),d->swrDrainNS.load(),d->producerEndNS.load(),d->ringDrainNS.load(),d->codecDrainFrames.load(),d->swrDrainFrames.load(),d->producedDigest.frames,d->consumedDigest.frames,d->producedDigest.full().c_str(),d->consumedDigest.full().c_str(),d->producedDigest.last().c_str(),d->consumedDigest.last().c_str());
        if(first.seekRequest)std::printf("{\"gate\":\"seek_pcm\",\"request_generation\":%llu,\"quiesced_generation\":%llu,\"ack_generation\":%llu,\"ready_generation\":%llu,\"produced_frames\":%llu,\"consumed_frames\":%llu,\"produced_pcm_sha256\":\"%s\",\"consumed_pcm_sha256\":\"%s\"}\n",first.seekRequest.load(),first.seekQuiesced.load(),first.seekAck.load(),first.seekDone.load(),first.seekProducedDigest.frames,first.seekConsumedDigest.frames,first.seekProducedDigest.full().c_str(),first.seekConsumedDigest.full().c_str());
        std::printf("{\"gate\":\"failure_latch\",\"first_transport_failure\":%d,\"next_transport_failure\":%d}\n",first.firstNonCancelTransportFailure.load(),next.firstNonCancelTransportFailure.load());
        if(first.seekRequest)std::printf("{\"gate\":\"seek_work\",\"decoder_context_recreations\":%llu,\"requested_preroll_seconds\":0.12,\"first_packet_relative_pts\":%.8f,\"converted_frames_trimmed_before_target\":%llu}\n",first.seekCodecResets.load(),first.seekFirstPacketPTS.load(),first.seekTrimmedFrames.load());
    }
    ~Session(){finish(1);unsigned destroyed=0;for(auto *d:{&first,&next})if(d->handle){MTStats stats{};mt_snapshot(d->handle,&stats);d->network=stats.network_bytes;mt_destroy(d->handle);d->handle=nullptr;destroyed++;}
        std::printf("{\"gate\":\"stream_cleanup\",\"handles_destroyed\":%u,\"decoder_threads_joined\":%u,\"output_starts\":%llu,\"output_stops\":%llu,\"premute_nonzero_mix_frames\":%llu,\"clipped_samples\":%llu,\"network_total_bytes\":%llu,\"outcome\":\"pass\"}\n",destroyed,joinedWorkers,starts.load(),stops.load(),preMuteNonzero.load(),clipped.load(),first.network.load()+next.network.load());
    }
};
bool Decoder::stopping()const{return cancel.load()||owner->cancelled.load();}
void Decoder::decode(double initialSeek){
    AVFormatContext *format=avformat_alloc_context();AVIOContext *io=nullptr;AVCodecContext *codec=nullptr;SwrContext *swr=nullptr;
    AVFrame *frame=av_frame_alloc();AVPacket *packet=av_packet_alloc();
    try{
        auto ok=[](int value){if(value<0)throw value;};require(format&&frame&&packet,"decoder allocation");
        format->probesize=65536;format->max_analyze_duration=AV_TIME_BASE;format->max_streams=4;format->interrupt_callback={interrupt,this};
        auto buffer=static_cast<uint8_t*>(av_malloc(4096));require(buffer,"AVIO buffer");
        io=avio_alloc_context(buffer,4096,0,this,read,nullptr,seek);if(!io){av_free(buffer);throw AVERROR(ENOMEM);}
        io->seekable=AVIO_SEEKABLE_NORMAL;format->pb=io;format->flags|=AVFMT_FLAG_CUSTOM_IO;
        ok(avformat_open_input(&format,nullptr,nullptr,nullptr));ok(avformat_find_stream_info(format,nullptr));
        int stream=av_find_best_stream(format,AVMEDIA_TYPE_AUDIO,-1,-1,nullptr,0);ok(stream);auto *track=format->streams[stream];auto *parameters=track->codecpar;
        require(parameters->codec_id==AV_CODEC_ID_AAC||parameters->codec_id==AV_CODEC_ID_OPUS,"codec scope");codecID=parameters->codec_id;
        codec=avcodec_alloc_context3(avcodec_find_decoder(parameters->codec_id));require(codec,"codec allocation");ok(avcodec_parameters_to_context(codec,parameters));
        codec->pkt_timebase=track->time_base;codec->thread_count=1;ok(avcodec_open2(codec,codec->codec,nullptr));
        require(codec->sample_rate>=8000&&codec->sample_rate<=192000&&codec->ch_layout.nb_channels>=1&&codec->ch_layout.nb_channels<=8,"format bounds");
        sourceRate=codec->sample_rate;sourceChannels=codec->ch_layout.nb_channels;
        // Positive presentation origins are relative to the first advertised
        // presentation timestamp. Negative codec preroll remains before zero.
        const double origin=track->start_time!=AV_NOPTS_VALUE?std::max(0.0,track->start_time*av_q2d(track->time_base)):0;
        require(std::isfinite(origin)&&origin<=1000000,"presentation origin bound");
        presentationOrigin=origin;
        AVChannelLayout stereo=AV_CHANNEL_LAYOUT_STEREO;ok(swr_alloc_set_opts2(&swr,&stereo,AV_SAMPLE_FMT_FLT,rate,&codec->ch_layout,codec->sample_fmt,codec->sample_rate,0,nullptr));ok(swr_init(swr));
        const double timebase=av_q2d(track->time_base);double target=initialSeek,nextPTS=0;
        // Never use a bitrate estimate as a hard presentation endpoint. For
        // negative/unknown origins let decoder pre-skip/discard-padding stand.
        const double endPTS=track->start_time!=AV_NOPTS_VALUE&&track->start_time>=0&&track->duration!=AV_NOPTS_VALUE&&format->duration_estimation_method!=AVFMT_DURATION_FROM_BITRATE?track->duration*timebase:INFINITY;
        uint64_t currentSeek=0;std::array<float,8192*2> pcm{};phase=Decoding;
        auto performSeek=[&](double seconds){auto at=(origin>0?track->start_time:0)+int64_t(std::max(0.0,seconds-.12)/timebase);ok(avformat_seek_file(format,stream,INT64_MIN,at,at,AVSEEK_FLAG_BACKWARD));
            // A new context makes each seek generation independent of decoded
            // prefix history. This is a bounded reset, not decoding from zero.
            avcodec_free_context(&codec);codec=avcodec_alloc_context3(avcodec_find_decoder(parameters->codec_id));require(codec,"seek codec allocation");
            ok(avcodec_parameters_to_context(codec,parameters));codec->pkt_timebase=track->time_base;codec->thread_count=1;ok(avcodec_open2(codec,codec->codec,nullptr));
            swr_free(&swr);ok(swr_alloc_set_opts2(&swr,&stereo,AV_SAMPLE_FMT_FLT,rate,&codec->ch_layout,codec->sample_fmt,codec->sample_rate,0,nullptr));ok(swr_init(swr));
            seekCodecResets++;nextPTS=seconds;target=seconds;seekFirstPTS=-1;};
        if(target>0)performSeek(target);
        auto publish=[&](int count,double pts,int stage){
            nextPTS=pts+double(count)/rate;for(int i=0;i<count*2;i++)require(std::isfinite(pcm[i]),"finite PCM");
            size_t begin=size_t(std::min(double(count),std::max(0.0,std::ceil((target-pts)*rate-.01))));
            if(currentSeek)seekTrimmedFrames+=begin;
            size_t end=size_t(std::max(0.0,std::min(double(count),std::ceil((endPTS-pts)*rate-.01))));
            if(begin>=end)return;
            uint64_t zero=0;if(firstPCM.compare_exchange_strong(zero,sp_now_ns()))pcmNetwork=network.load();
            if(seekFirstPTS<0)seekFirstPTS=pts+double(begin)/rate;
            while(begin<end&&!stopping()&&seekRequest.load()==currentSeek){
                size_t count=ring.push(pcm.data()+begin*2,end-begin);
                if(count){producedDigest.add(pcm.data()+begin*2,count);if(currentSeek)seekProducedDigest.add(pcm.data()+begin*2,count);produced+=count;if(stage==CodecDrain)codecDrainFrames+=count;if(stage==SwrDrain)swrDrainFrames+=count;}
                begin+=count;require(produced<=rate*900,"output bound");if(!count)pause_ms(1);
            }
            if(currentSeek&&ring.size()>=8192)seekDone=currentSeek;
        };
        auto receive=[&](int stage){int code=AVERROR(EAGAIN);
            while(!stopping()&&seekRequest.load()==currentSeek&&(code=avcodec_receive_frame(codec,frame))>=0){
                require(swr_get_out_samples(swr,frame->nb_samples)<=8192,"converted block bound");
                double pts=frame->pts==AV_NOPTS_VALUE?nextPTS:frame->pts*timebase-origin-double(swr_get_delay(swr,codec->sample_rate))/codec->sample_rate;
                uint8_t *out=reinterpret_cast<uint8_t*>(pcm.data());int count=swr_convert(swr,&out,8192,const_cast<const uint8_t**>(frame->extended_data),frame->nb_samples);ok(count);
                publish(count,pts,stage);av_frame_unref(frame);
            }
            if(!stopping()&&seekRequest.load()==currentSeek&&code<0&&code!=AVERROR(EAGAIN)&&code!=AVERROR_EOF)throw code;
            return code;
        };
        while(!stopping()){
            if(seekRequest.load()!=currentSeek){auto requested=seekRequest.load();seekQuiesced.store(requested,std::memory_order_release);
                while(seekAck.load(std::memory_order_acquire)<requested&&!stopping())pause_ms(1);
                if(stopping())break;performSeek(seekTarget.load());currentSeek=requested;
            }
            int code=av_read_frame(format,packet);
            if(code==AVERROR_EOF){
                // Some demuxers return EOF after an underlying I/O failure.
                // A partial block or transport error must never become normal EOF.
                if(transportStatus<0)throw AVERROR(EIO);
                if(io->error<0&&io->error!=AVERROR_EOF)throw io->error;
                {std::lock_guard<std::mutex> lock(control);if(seekRequest.load()!=currentSeek)continue;phase=CodecDrain;codecDrainNS=sp_now_ns();}
                ok(avcodec_send_packet(codec,nullptr));int drained=receive(CodecDrain);if(stopping())break;require(drained==AVERROR_EOF,"codec did not drain to EOF");
                phase=SwrDrain;swrDrainNS=sp_now_ns();
                for(;;){if(stopping())break;uint8_t *out=reinterpret_cast<uint8_t*>(pcm.data());int count=swr_convert(swr,&out,8192,nullptr,0);ok(count);if(!count)break;publish(count,nextPTS,SwrDrain);}
                if(stopping())break;
                if(currentSeek){require(seekProducedDigest.frames>0,"seek has no output");seekDone=currentSeek;} // A valid short tail need not fill the prefill threshold.
                sealedWrite=ring.write.load();producerEndNS=sp_now_ns();phase.store(Ended,std::memory_order_release);break;
            }
            ok(code);
            if(packet->stream_index==stream){if(currentSeek&&seekFirstPacketPTS<0&&packet->pts!=AV_NOPTS_VALUE)seekFirstPacketPTS=packet->pts*timebase-origin;
                code=avcodec_send_packet(codec,packet);if(code==AVERROR(EAGAIN)){receive(Decoding);code=avcodec_send_packet(codec,packet);}ok(code);receive(Decoding);}
            av_packet_unref(packet);
        }
        if(stopping()&&phase!=Ended){if(firstNonCancelTransportFailure){error=AVERROR(EIO);phase=Failed;}else phase=Cancelled;}
    }catch(int code){if(stopping()&&!firstNonCancelTransportFailure)phase=Cancelled;else{error=code;phase=Failed;}}
     catch(...){if(stopping()&&!firstNonCancelTransportFailure)phase=Cancelled;else{error=AVERROR_UNKNOWN;phase=Failed;}}
    av_frame_free(&frame);av_packet_free(&packet);swr_free(&swr);avcodec_free_context(&codec);avformat_close_input(&format);
    if(io){av_freep(&io->buffer);avio_context_free(&io);}
}
void verifyEarly(Decoder &d){require(d.firstPCM>0&&d.firstCallback>0,"PCM and callback observed");require(d.pcmNetwork<d.total&&d.callbackNetworkUpper<d.total,"whole media fetched before render");require(d.bufferHigh<=window&&d.ring.high<=capacity,"bounded buffers");require(d.error==0,"decoder healthy");}
}
int main(int argc,char **argv){
    av_log_set_level(AV_LOG_QUIET);if(argc<3)return 64;bool live=strcmp(argv[1],"public-opus")==0;
    if((live&&argc<4)||(!live&&argc<5))return 64;const char *mode=live?"public-opus":argv[2];Session session(sp_now_ns());
    auto natural=[&]{uint64_t deadline=sp_now_ns()+10ull*1000000000;
        while(!session.first.ringDrainNS&&!session.cancelled){require(sp_now_ns()<deadline,"natural drain timeout");pause_ms(2);}
        require(session.first.ringDrainNS&&session.first.phase==Ended&&!session.first.error,"normal end state");session.finish(5);
        require(session.reason==5&&session.first.codecDrainNS&&session.first.swrDrainNS&&session.first.producerEndNS,"drain sequence");
        require(session.first.ring.read==session.first.sealedWrite&&session.first.ring.size()==0,"sealed ring not drained");};
    try{
        SPSource source=live?sp_resolve(argv[2],0,"opus"):sp_local_window(argv[3],std::strtoull(argv[4],nullptr,10),!strcmp(mode,"late-failure")?32768:262144);
        session.attach(session.first,source);if(!strcmp(mode,"failure-cancel-race"))session.first.holdFailureReturn=true;session.first.launch(0);
        if(!strcmp(mode,"failure-cancel-race")){
            uint64_t until=sp_now_ns()+3ull*1000000000;while(!session.first.failureReturnHeld&&sp_now_ns()<until)pause_ms(1);
            require(session.first.failureReturnHeld&&session.first.firstNonCancelTransportFailure&&session.first.error==0,"failure return barrier missed");
            session.requestCancel(6);session.finish(6);require(session.reason==4&&session.first.phase==Failed&&session.first.error,"cancel hid an earlier failure");
            std::puts("{\"gate\":\"failure_cancel_race\",\"error_observed_before_stop\":true,\"requested_stop_reason\":\"bounded_probe_complete\",\"final_reason\":\"input_failed\"}");
        }else if(!strcmp(mode,"full-ring-cancel")){
            session.prepare(session.first);pause_ms(80);require(session.first.ring.size()==capacity,"ring not full");auto start=sp_now_ns();session.finish(1);
            std::printf("{\"gate\":\"cancel_join\",\"elapsed_ms\":%.3f,\"was_full\":true}\n",(sp_now_ns()-start)/1e6);
        }else if(!strcmp(mode,"disconnect")){
            bool failed=false;try{session.prepare(session.first);}catch(...){failed=true;}
            require(failed&&session.first.error!=0,"expected input rejection");session.finish(4);
        }else{
            session.prepare(session.first);pause_ms(80);auto before=session.first.network.load();pause_ms(80);require(before==session.first.network.load(),"backpressure");session.startOutput();
            if(!strcmp(mode,"eof")||!strcmp(mode,"terminal-seek-reject")){
                if(!strcmp(mode,"terminal-seek-reject")){require(session.first.phase==Ended&&session.first.ring.size()>0,"producer/ring end separation");require(session.requestSeek(.01)==0,"seek accepted after seal");std::puts("{\"gate\":\"terminal_seek\",\"outcome\":\"explicit_rejection\"}");}
                natural();require(session.first.producedDigest.frames==session.first.consumedDigest.frames&&session.first.producedDigest.full()==session.first.consumedDigest.full(),"ring lost or changed EOF PCM");
                require(session.first.producedDigest.last()==session.first.consumedDigest.last(),"ring tail changed");
            }else if(!strcmp(mode,"late-failure")){
                pause_ms(400);require(session.first.firstCallback>0,"no output before failure");uint64_t until=sp_now_ns()+7ull*1000000000;
                while(!session.first.error&&sp_now_ns()<until)pause_ms(10);
                require(session.first.error&&session.first.transportStatus<0,"second-range failure not observed");session.finish(4);require(session.reason==4,"failure classification");
                std::puts("{\"gate\":\"late_next_failure\",\"output_started_first\":true,\"next_deliberately_pending\":true,\"outcome\":\"expected_failure\"}");
            }else if(!strcmp(mode,"active-cancel")){
                pause_ms(400);verifyEarly(session.first);session.finish(1);auto consumed=session.first.consumed.load();pause_ms(50);require(consumed==session.first.consumed,"PCM consumed after stop/join");
                std::puts("{\"gate\":\"active_cancel\",\"post_join_consumption_frames\":0}");
            }else if(live||!strcmp(mode,"tail-seek")||!strcmp(mode,"publish-seek")||!strcmp(mode,"timeline-seek")){
                pause_ms(400);if(!strcmp(mode,"timeline-seek")){require(session.first.firstCallback>0,"timeline input not consumed");std::puts("{\"gate\":\"small_timeline_fixture\",\"partial_fetch_proved\":false}");}else verifyEarly(session.first);
                double target=live?std::strtod(argv[3],nullptr):std::strtod(argv[5],nullptr);
                if(!strcmp(mode,"publish-seek")){
                    session.first.ring.holdNextPublish=true;uint64_t until=sp_now_ns()+1000000000;
                    while(!session.first.ring.publishHeld&&sp_now_ns()<until)pause_ms(1);require(session.first.ring.publishHeld,"publish barrier missed");
                    auto generation=session.requestSeek(target);require(generation>0,"seek rejected before barrier");pause_ms(30);
                    require(session.first.seekAck<generation&&session.first.seekQuiesced<generation,"ack bypassed active producer");auto count=session.first.consumed.load();pause_ms(20);require(session.first.consumed==count,"old PCM consumed while seek pending");
                    session.first.ring.releasePublish=true;session.waitSeek(generation);std::puts("{\"gate\":\"seek_publish_barrier\",\"ack_waited_for_producer\":true,\"old_consumption_stopped\":true}");
                }else session.seekFirst(target);
                natural();require(session.first.seekDone==1&&session.first.seekProducedDigest.frames>0,"seek not completed");
                require(session.first.seekProducedDigest.full()==session.first.seekConsumedDigest.full()&&session.first.seekProducedDigest.frames==session.first.seekConsumedDigest.frames,"post-seek PCM changed or lost");
                if(live)require(session.first.codecID==AV_CODEC_ID_OPUS,"public decoder did not use Opus");
            }else if(!strcmp(mode,"late")){
                pause_ms(400);verifyEarly(session.first);require(!session.next.handle,"next already prepared");pause_ms(200);
                session.prepareNext(sp_local(argv[5],std::strtoull(argv[6],nullptr,10)));pause_ms(1000);auto before=session.first.consumed.load(),next=session.next.consumed.load();pause_ms(300);
                require(session.transitions==1&&session.first.consumed==before&&session.next.consumed>next,"transition ownership");verifyEarly(session.next);session.finish(6);
            }else throw std::runtime_error("unknown mode");
        }
        bool expectedFailure=!strcmp(mode,"disconnect")||!strcmp(mode,"late-failure")||!strcmp(mode,"failure-cancel-race");
        if(!expectedFailure)require(!session.first.error&&!session.next.error&&!session.first.firstNonCancelTransportFailure&&!session.next.firstNonCancelTransportFailure,"input error cannot pass");
        int expectedReason=expectedFailure?4:(!strcmp(mode,"full-ring-cancel")||!strcmp(mode,"active-cancel"))?1:!strcmp(mode,"late")?6:5;
        require(session.reason==expectedReason,"unexpected termination reason cannot pass");
        require(session.first.network+session.next.network<=32ull*1024*1024,"network total");session.report(mode);
        std::printf("{\"gate\":\"streaming_proof\",\"outcome\":\"%s\",\"media_file_written\":false,\"human_audibility\":false}\n",expectedFailure?"expected_failure_observed":"pass");return 0;
    }catch(const std::exception &error){session.finish(7);session.report(mode);std::fprintf(stderr,"stream proof failed: %s\n",error.what());return 1;}
}
