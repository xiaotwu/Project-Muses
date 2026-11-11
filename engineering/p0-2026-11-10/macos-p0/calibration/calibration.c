// SPDX-License-Identifier: MIT
#include "calibration.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

void cal_gate_init(CalGate *g){atomic_init(&g->packed,CAL_IDLE);}
uint64_t cal_gate_begin(CalGate *g){uint64_t old=atomic_load(&g->packed);if((old&7)!=CAL_IDLE||(old>>3)==(UINT64_MAX>>3))return 0;uint64_t n=(old>>3)+1;return atomic_compare_exchange_strong(&g->packed,&old,(n<<3)|CAL_PERMISSION)?n:0;}
bool cal_gate_start(CalGate *g,uint64_t n){uint64_t expected=(n<<3)|CAL_PERMISSION;return n&&atomic_compare_exchange_strong(&g->packed,&expected,(n<<3)|CAL_RUNNING);}
bool cal_gate_cancel(CalGate *g){uint64_t old=atomic_load(&g->packed);while((old&7)==CAL_PERMISSION||(old&7)==CAL_RUNNING||(old&7)==CAL_FINISHING){if(atomic_compare_exchange_weak(&g->packed,&old,(old&~7ull)|CAL_CANCELLED))return true;}return false;}
bool cal_gate_cancel_generation(CalGate *g,uint64_t n){uint64_t old=atomic_load(&g->packed);while((old>>3)==n&&((old&7)==CAL_PERMISSION||(old&7)==CAL_RUNNING||(old&7)==CAL_FINISHING)){if(atomic_compare_exchange_weak(&g->packed,&old,(old&~7ull)|CAL_CANCELLED))return true;}return false;}
bool cal_gate_finish(CalGate *g,uint64_t n){uint64_t old=atomic_load(&g->packed);while((old>>3)==n){if((old&7)==CAL_FINISHING)return true;if((old&7)!=CAL_PERMISSION&&(old&7)!=CAL_RUNNING)return false;if(atomic_compare_exchange_weak(&g->packed,&old,(n<<3)|CAL_FINISHING))return true;}return false;}
bool cal_gate_reset(CalGate *g,uint64_t n){uint64_t old=atomic_load(&g->packed);while(n&&(old>>3)==n&&((old&7)==CAL_FINISHING||(old&7)==CAL_CANCELLED)){if(atomic_compare_exchange_weak(&g->packed,&old,n<<3))return true;}return false;}
bool cal_gate_running(const CalGate *g,uint64_t n){return n&&atomic_load(&g->packed)==((n<<3)|CAL_RUNNING);}
bool cal_gate_finishing(const CalGate *g,uint64_t n){return n&&atomic_load(&g->packed)==((n<<3)|CAL_FINISHING);}
bool cal_gate_commit_result(CalGate *g,uint64_t n){uint64_t expected=(n<<3)|CAL_FINISHING;return n&&atomic_compare_exchange_strong(&g->packed,&expected,n<<3);}

static uint32_t random_word(uint32_t *s){*s^=*s<<13;*s^=*s>>17;*s^=*s<<5;return *s;}
void cal_wipe(void *bytes,size_t count){volatile unsigned char *p=bytes;while(count--)*p++=0;}
bool cal_make_marker(unsigned marker,double rate,float *output,size_t frames){
    if(marker>1||!output||!isfinite(rate)||rate<6000||rate>192000||frames!=(size_t)llround(CAL_MARKER_SECONDS*rate))return false;
    uint32_t seed=marker?0x8b6c71e5u:0x215acb47u;double frequency[32],phase[32];
    for(unsigned k=0;k<32;k++){frequency[k]=550.0+56.0*k+(random_word(&seed)%1000)/1000.0*56.0;phase[k]=(random_word(&seed)/(double)UINT32_MAX)*2*M_PI;}
    for(size_t i=0;i<frames;i++){
        double t=i/rate,edge=fmin(t,CAL_MARKER_SECONDS-t),envelope=edge<.005?.5-.5*cos(M_PI*edge/.005):1,sum=0;
        for(unsigned k=0;k<32;k++)sum+=sin(2*M_PI*frequency[k]*t+phase[k]);
        output[i]=(float)(sum*.005*envelope); // <= 0.16 peak; approx 0.02 RMS.
    }return true;
}

static CalResult failure(const char *reason){CalResult r={0};r.reason=reason;r.confidence="invalid";return r;}
static bool valid_rate(double rate){return isfinite(rate)&&rate>=16000&&rate<=192000;}
static double linear(const float *samples,size_t n,double position){size_t i=(size_t)position;double fraction=position-i;return i+1<n?samples[i]*(1-fraction)+samples[i+1]*fraction:samples[n-1];}

static bool clock_fit(const CalCapture *c,CalResult *result,double *seconds_per_frame,double *intercept){
    if(!c->anchors||c->anchor_count<4||c->anchor_count>CAL_MAX_ANCHORS)return false;
    const CalAnchor *a=c->anchors;if(a[0].frame!=0)return false;double sx=0,sy=0,sxx=0,sxy=0,n=c->anchor_count;
    for(size_t i=0;i<c->anchor_count;i++){
        if(a[i].frame>=c->count||!a[i].host_ns||(i&&(a[i].frame<=a[i-1].frame||a[i].host_ns<=a[i-1].host_ns)))return false;
        double x=(a[i].frame-a[0].frame)/c->sample_rate,y=(a[i].host_ns-a[0].host_ns)/1e9;
        if(i&&fabs((a[i].host_ns-a[i-1].host_ns)/1e9-(a[i].frame-a[i-1].frame)/c->sample_rate)>.003)return false;
        sx+=x;sy+=y;sxx+=x*x;sxy+=x*y;
    }
    if((a[c->anchor_count-1].frame-a[0].frame)/c->sample_rate<2)return false;
    double denominator=n*sxx-sx*sx;if(denominator<=0)return false;
    double scale=(n*sxy-sx*sy)/denominator,offset=(sy-scale*sx)/n,max_residual=0;
    for(size_t i=0;i<c->anchor_count;i++){double x=(a[i].frame-a[0].frame)/c->sample_rate,y=(a[i].host_ns-a[0].host_ns)/1e9;max_residual=fmax(max_residual,fabs(y-(offset+scale*x)));}
    result->clock_drift_ppm=(scale-1)*1e6;result->clock_max_residual_ms=max_residual*1000;
    if(fabs(result->clock_drift_ppm)>2000||max_residual>.001)return false;
    *seconds_per_frame=scale/c->sample_rate;*intercept=offset-a[0].frame*(*seconds_per_frame);
    return true;
}

CalResult cal_analyze(const CalCapture *c){
    if(!c||!c->samples||!valid_rate(c->sample_rate)||c->count<3.5*c->sample_rate||c->count>CAL_MAX_SECONDS*c->sample_rate)return failure("capture_bounds");
    size_t n=(size_t)floor(c->count*CAL_ANALYSIS_RATE/c->sample_rate),m=(size_t)llround(CAL_MARKER_SECONDS*CAL_ANALYSIS_RATE);
    size_t audio_bytes=c->count*sizeof(float)+(n+2*m)*sizeof(float);
    if(audio_bytes>CAL_AUDIO_BYTES)return failure("audio_memory_limit");
    CalResult result=failure("measurement_invalid");result.working_audio_bytes=audio_bytes;
    if(c->should_cancel&&c->should_cancel(c->cancel_opaque))return failure("cancelled");
    double slope,intercept;if(!clock_fit(c,&result,&slope,&intercept)){result.reason="clock_invalid";return result;}
    size_t clipped=0;for(size_t i=0;i<c->count;i++){if(!isfinite(c->samples[i]))return failure("nonfinite_sample");if(fabs(c->samples[i])>=.98)clipped++;}
    result.clipped_fraction=clipped/(double)c->count;if(result.clipped_fraction>.005){result.reason="clipping";return result;}
    float *down=calloc(n,sizeof(float)),*reference=calloc(2*m,sizeof(float));
    if(!down||!reference){free(down);free(reference);result.reason="allocation_failed";return result;}
    // Frozen linear rate conversion. Markers occupy 550..2342 Hz (< 3 kHz).
    // Unfiltered high-frequency ambient noise may reduce confidence; it cannot
    // supply a valid matching sequence. This is not a general music resampler.
    for(size_t i=0;i<n;i++)down[i]=(float)linear(c->samples,c->count,i*c->sample_rate/CAL_ANALYSIS_RATE);
    size_t noise_n=(size_t)(.25*CAL_ANALYSIS_RATE);double noise=0;for(size_t i=0;i<noise_n;i++)noise+=down[i]*down[i];result.noise_rms=sqrt(noise/noise_n);
    for(unsigned marker=0;marker<2;marker++){
        float *r=reference+marker*m;cal_make_marker(marker,CAL_ANALYSIS_RATE,r,m);
        double mean=0,energy=0;for(size_t j=0;j<m;j++)mean+=r[j];mean/=m;
        for(size_t j=0;j<m;j++){r[j]-=(float)mean;energy+=r[j]*r[j];}
        double best=-1;size_t best_index=0;
        // Two passes avoid retaining an unbounded correlation trace.
        for(unsigned pass=0;pass<2;pass++){
            double second=-1;
            for(size_t i=noise_n;i+m<=n;i++){
                if(!(i&63)&&c->should_cancel&&c->should_cancel(c->cancel_opaque)){result.reason="cancelled";goto done;}
                if(pass&&llabs((long long)i-(long long)best_index)<(long long)(.010*CAL_ANALYSIS_RATE))continue;
                double dot=0,sy=0,syy=0;for(size_t j=0;j<m;j++){double y=down[i+j];dot+=y*r[j];sy+=y;syy+=y*y;}
                double variance=syy-sy*sy/m,score=variance>1e-20?fabs(dot)/sqrt(energy*variance):0;
                if(!pass&&score>best){best=score;best_index=i;}else if(pass&&score>second)second=score;
            }
            if(pass)result.markers[marker].runner_up_correlation=fmax(0,second);
        }
        CalMatch *match=&result.markers[marker];match->correlation=fmax(0,best);match->reference_frame=best_index*c->sample_rate/CAL_ANALYSIS_RATE;
        double rms=0;for(size_t j=0;j<m;j++)rms+=down[best_index+j]*down[best_index+j];match->signal_rms=sqrt(rms/m);
        if(best<.65){result.reason="sequence_not_matched";goto done;}
        if(match->runner_up_correlation>best/1.6){result.reason="ambiguous_sequence";goto done;}
        if(match->signal_rms<fmax(.0001,result.noise_rms*5)){result.reason="signal_below_frozen_noise_gate";goto done;}
        size_t window=(size_t)(.002*CAL_ANALYSIS_RATE),onset=SIZE_MAX;double threshold=fmax(.0001,result.noise_rms*5);
        for(size_t j=0;j+3*window<=m;j+=window){bool sustained=true;for(unsigned w=0;w<3;w++){double e=0;for(size_t k=0;k<window;k++){double v=down[best_index+j+w*window+k];e+=v*v;}if(sqrt(e/window)<threshold)sustained=false;}if(sustained){onset=best_index+j;break;}}
        if(onset==SIZE_MAX){result.reason="onset_not_sustained";goto done;}
        match->onset_frame=onset*c->sample_rate/CAL_ANALYSIS_RATE;
        match->reference_host_ns=c->anchors[0].host_ns+(uint64_t)llround((intercept+match->reference_frame*slope)*1e9);
        match->onset_host_ns=c->anchors[0].host_ns+(uint64_t)llround((intercept+match->onset_frame*slope)*1e9);
    }
    if(fabs((result.markers[1].reference_frame-result.markers[0].reference_frame)/c->sample_rate-CAL_MARKER_GAP_SECONDS)>.020){result.reason="marker_spacing_invalid";goto done;}
    result.detector_error_bound_ms=2.0+1000/CAL_ANALYSIS_RATE+1000/c->sample_rate+result.clock_max_residual_ms;
    if(c->should_cancel&&c->should_cancel(c->cancel_opaque)){result.reason="cancelled";goto done;}
    result.valid=true;result.reason="matched_two_markers";result.confidence="two_distinct_markers_above_frozen_thresholds";
done:cal_wipe(down,n*sizeof(float));free(down);free(reference);return result;
}
