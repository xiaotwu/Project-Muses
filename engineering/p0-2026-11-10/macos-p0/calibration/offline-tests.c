// SPDX-License-Identifier: MIT
// Synthetic PCM only: this executable does not link an audio-device API.
#include "calibration.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>

static unsigned Checks,Failures;
static void check(bool value,const char *label){Checks++;if(!value)Failures++;printf("{\"case\":\"%s\",\"outcome\":\"%s\"}\n",label,value?"pass":"fail");}
static uint32_t rng(uint32_t *x){*x=*x*1664525u+1013904223u;return *x;}
static double sample_at(const float *pcm,size_t count,double time,double rate){double p=time*rate;if(p<0||p>=count-1)return 0;size_t n=(size_t)p;return pcm[n]+(pcm[n+1]-pcm[n])*(p-n);}
typedef struct{float *pcm;CalAnchor *anchors;CalCapture capture;double first,second;} Fixture;
static Fixture fixture(double inputRate,double outputRate,double delay,double gain,double noise,unsigned mode,double drift){
    Fixture f={0};size_t frames=(size_t)(5*inputRate),markerFrames=(size_t)llround(CAL_MARKER_SECONDS*outputRate);f.pcm=calloc(frames,sizeof(float));
    float *a=calloc(markerFrames,sizeof(float)),*b=calloc(markerFrames,sizeof(float));cal_make_marker(0,outputRate,a,markerFrames);cal_make_marker(1,outputRate,b,markerFrames);
    if(mode==2)for(size_t i=0;i<markerFrames;i++){a[i]=.03*sin(2*M_PI*990*i/outputRate);b[i]=.03*sin(2*M_PI*1350*i/outputRate);}
    f.first=.5+delay;f.second=f.first+CAL_MARKER_GAP_SECONDS+(mode==5?.25:0);uint32_t random=0x71ab218f;
    for(size_t i=0;i<frames;i++){
        double t=i/inputRate,y=((rng(&random)/(double)UINT32_MAX)*2-1)*noise;
        if(mode!=1){y+=gain*sample_at(a,markerFrames,t-f.first,outputRate);if(mode!=3)y+=gain*sample_at(b,markerFrames,t-f.second,outputRate);}
        if(mode==4){y+=gain*sample_at(a,markerFrames,t-f.first-.35,outputRate);y+=gain*sample_at(b,markerFrames,t-f.second-.35,outputRate);}
        if(mode==6){y+=gain*.12*sample_at(a,markerFrames,t-f.first-.007,outputRate);y+=gain*.12*sample_at(b,markerFrames,t-f.second-.007,outputRate);}
        f.pcm[i]=(float)y;
    }
    free(a);free(b);size_t n=(frames+511)/512;f.anchors=calloc(n,sizeof(CalAnchor));
    for(size_t i=0;i<n;i++){f.anchors[i].frame=i*512;f.anchors[i].host_ns=1000000000000ull+(uint64_t)llround(i*512/inputRate*(1+drift/1e6)*1e9);}
    f.capture=(CalCapture){f.pcm,frames,inputRate,f.anchors,n,NULL,NULL};return f;
}
static void discard(Fixture *f){cal_wipe(f->pcm,f->capture.count*sizeof(float));free(f->pcm);free(f->anchors);}
static void positive(const char *name,double in,double out,double delay,double gain,double noise,unsigned mode,double drift){
    Fixture f=fixture(in,out,delay,gain,noise,mode,drift);CalResult result=cal_analyze(&f.capture);
    double error0=result.markers[0].reference_frame/in-f.first,error1=result.markers[1].reference_frame/in-f.second;
    bool valid=result.valid&&fabs(error0)<.001&&fabs(error1)<.001&&fabs(result.clock_drift_ppm-drift)<.1&&result.working_audio_bytes<CAL_AUDIO_BYTES&&result.detector_error_bound_ms>2;
    check(valid,name);printf("{\"measurement\":\"%s\",\"reason\":\"%s\",\"known_delay_ms\":%.6f,\"reference_error_us\":[%.6f,%.6f],\"correlation\":[%.6f,%.6f],\"runner_up\":[%.6f,%.6f],\"clock_drift_ppm\":%.6f,\"detector_bound_ms\":%.6f,\"audio_bytes\":%zu}\n",name,result.reason,delay*1000,error0*1e6,error1*1e6,result.markers[0].correlation,result.markers[1].correlation,result.markers[0].runner_up_correlation,result.markers[1].runner_up_correlation,result.clock_drift_ppm,result.detector_error_bound_ms,result.working_audio_bytes);
    discard(&f);
}
static void negative(const char *name,unsigned mode,double noise){Fixture f=fixture(48000,48000,.12,1,noise,mode,0);CalResult r=cal_analyze(&f.capture);check(!r.valid,name);printf("{\"rejection\":\"%s\",\"reason\":\"%s\"}\n",name,r.reason);discard(&f);}
static bool cancel_analysis(void *opaque){unsigned *calls=opaque;return ++*calls>8;}
static void gates(void){CalGate g;cal_gate_init(&g);check(!cal_gate_cancel(&g),"idle_cancel_noop");uint64_t one=cal_gate_begin(&g);check(one==1,"explicit_begin");check(!cal_gate_begin(&g),"permission_busy");check(!cal_gate_running(&g,one),"permission_has_no_audio");check(cal_gate_cancel(&g),"cancel_pending_permission");check(!cal_gate_start(&g,one),"late_permission_cannot_start");check(!cal_gate_finish(&g,one)&&cal_gate_reset(&g,one),"permission_cancel_teardown");uint64_t two=cal_gate_begin(&g);check(two==2,"new_generation");check(!cal_gate_start(&g,one)&&!cal_gate_cancel_generation(&g,one)&&!cal_gate_finish(&g,one)&&!cal_gate_reset(&g,one),"old_callbacks_rejected");check(cal_gate_start(&g,two)&&cal_gate_running(&g,two),"granted_generation_starts");check(!cal_gate_begin(&g),"running_busy");check(cal_gate_cancel_generation(&g,two)&&!cal_gate_running(&g,two),"cancel_silences_shared_gate");check(!cal_gate_finish(&g,two)&&cal_gate_reset(&g,two),"cancel_to_idle");uint64_t three=cal_gate_begin(&g);check(three==3&&cal_gate_start(&g,three),"fresh_after_cancel");check(cal_gate_finish(&g,three)&&!cal_gate_running(&g,three)&&cal_gate_reset(&g,three),"normal_completion_to_idle");}
int main(void){struct rlimit core={0,0};setrlimit(RLIMIT_CORE,&core);setvbuf(stdout,NULL,_IOLBF,0);gates();
    positive("48k_known_delay",48000,48000,.037,1,.0002,0,0);
    positive("44k1_capture_48k_output",44100,48000,.12345,.8,.0002,0,0);
    positive("48k_capture_44k1_output",48000,44100,.08529,.8,.0002,0,0);
    positive("96k_capture",96000,48000,.2013,1,.0002,0,0);
    positive("16k_capture",16000,48000,.1167,1,.0002,0,0);
    positive("192k_capture_memory_bound",192000,48000,.0717,1,.0002,0,0);
    positive("low_gain",48000,48000,.15,.12,.00002,0,0);
    positive("moderate_noise",48000,48000,.12,1,.003,0,0);
    positive("weak_room_echo",48000,48000,.12,1,.0002,6,0);
    positive("inverted_polarity",48000,48000,.12,-1,.0002,0,0);
    positive("clock_drift_150ppm",48000,48000,.12,1,.0002,0,150);
    negative("silence",1,0);negative("noise_only",1,.003);negative("wrong_sequence",2,.0002);negative("missing_second_marker",3,.0002);negative("duplicate_sequence",4,.0002);negative("wrong_marker_spacing",5,.0002);negative("noise_gate_rejects_low_snr",0,.04);
    Fixture f=fixture(48000,48000,.12,1,.0002,0,0);CalCapture c=f.capture;c.count=(size_t)(8.01*c.sample_rate);check(!cal_analyze(&c).valid,"duration_over_8s_rejected");c=f.capture;c.sample_rate=384000;check(!cal_analyze(&c).valid,"sample_rate_over_limit_rejected");c=f.capture;c.sample_rate=NAN;check(!cal_analyze(&c).valid,"nan_rate_rejected");c=f.capture;c.anchor_count=3;check(!cal_analyze(&c).valid,"insufficient_clock_anchors_rejected");
    f.anchors[2].host_ns=f.anchors[1].host_ns-1;check(!cal_analyze(&f.capture).valid,"backward_capture_clock_rejected");discard(&f);
    f=fixture(48000,48000,.12,1,.0002,0,0);f.anchors[10].host_ns+=20000000;check(!cal_analyze(&f.capture).valid,"clock_discontinuity_rejected");discard(&f);
    f=fixture(48000,48000,.12,1,.0002,0,4000);check(!cal_analyze(&f.capture).valid,"excess_clock_drift_rejected");discard(&f);
    f=fixture(48000,48000,.12,1,.0002,0,0);f.pcm[0]=NAN;check(!cal_analyze(&f.capture).valid,"nonfinite_pcm_rejected");for(size_t i=0;i<f.capture.count;i++)f.pcm[i]=1;check(!cal_analyze(&f.capture).valid,"clipping_rejected");discard(&f);
    f=fixture(48000,48000,.12,1,.0002,0,0);unsigned calls=0;f.capture.should_cancel=cancel_analysis;f.capture.cancel_opaque=&calls;CalResult cancelled=cal_analyze(&f.capture);check(!cancelled.valid&&!strcmp(cancelled.reason,"cancelled")&&calls==9,"analysis_cancels_during_correlation");discard(&f);
    CalGate gate;cal_gate_init(&gate);uint64_t generation=cal_gate_begin(&gate);check(cal_gate_start(&gate,generation)&&cal_gate_finish(&gate,generation)&&cal_gate_finishing(&gate,generation)&&cal_gate_cancel(&gate)&&!cal_gate_finishing(&gate,generation)&&cal_gate_reset(&gate,generation),"cancel_during_analysis_resets");
    generation=cal_gate_begin(&gate);cal_gate_start(&gate,generation);bool timerSawRunning=cal_gate_running(&gate,generation);cal_gate_cancel(&gate);
    check(timerSawRunning&&!cal_gate_finish(&gate,generation)&&!cal_gate_finishing(&gate,generation)&&!cal_gate_commit_result(&gate,generation)&&cal_gate_reset(&gate,generation),"timer_read_cancel_finish_cannot_resurrect");
    generation=cal_gate_begin(&gate);check(cal_gate_start(&gate,generation)&&cal_gate_finish(&gate,generation)&&cal_gate_commit_result(&gate,generation)&&!cal_gate_cancel(&gate),"completed_result_commit_is_atomic");
    struct rusage usage;getrusage(RUSAGE_SELF,&usage);printf("{\"summary\":\"%s\",\"checks\":%u,\"failures\":%u,\"maxrss_bytes\":%ld,\"device_api_linked\":false,\"recorded\":false,\"audible_output\":false}\n",Failures?"fail":"pass",Checks,Failures,usage.ru_maxrss);return Failures?1:0;
}
