// MIT. Read-only complete public files, shared CoreAudio, ALWAYS muted.
#include "../../audio/p0_audio.h"
#include <chrono>
#include <cstdio>
#include <stdexcept>
#include <thread>

using Clock=std::chrono::steady_clock;
static void check(bool value,const char *message){if(!value)throw std::runtime_error(message);}
static MusesP0AudioSnapshot snap(void *session){MusesP0AudioSnapshot s{};check(muses_p0_audio_snapshot(session,&s)==0,"snapshot");return s;}
int main(int argc,char **argv){
    if(argc!=3)return 64;void *session=nullptr;
    try {
        int error=0;session=muses_p0_audio_start(argv[1],6,0,&error);check(session && error==0,"muted real AAC start");
        auto started=Clock::now();std::this_thread::sleep_for(std::chrono::milliseconds(300));
        auto first=snap(session);check(first.first_consumed_frames>0 && first.next_consumed_frames==0,"first source consumption");
        check(muses_p0_audio_prepare_next(session,argv[2],500,1000)==0,"fresh real Opus prepare");
        std::this_thread::sleep_until(started+std::chrono::milliseconds(2500));auto after=snap(session);
        std::this_thread::sleep_until(started+std::chrono::milliseconds(3000));auto later=snap(session);
        check(after.clock_frames>after.transition_end_frame && later.clock_frames>after.clock_frames,"one advancing transition clock");
        check(after.transitions==1 && later.transitions==1,"exactly one transition");
        check(after.first_consumed_frames==later.first_consumed_frames && later.next_consumed_frames>after.next_consumed_frames,"post-fade source ownership");
        check(later.next_ready && !later.first_error && !later.next_error,"both real decoders healthy");
        check(!later.underflow_frames && !later.clipped_samples && !later.nonzero_output_frames,"muted unclipped continuous callback");
        std::this_thread::sleep_until(started+std::chrono::milliseconds(6300));auto end=snap(session);
        check(end.timed_stop && end.starts==1 && end.stops==1,"native six second watchdog");
        auto stoppedClock=end.clock_frames;std::this_thread::sleep_for(std::chrono::milliseconds(100));check(snap(session).clock_frames==stoppedClock,"stopped clock");
        muses_p0_audio_stop(session);session=nullptr;
        std::printf("{\"gate\":\"real_media_audio_abi\",\"outcome\":\"pass\",\"first_codec\":\"AAC_6ch_48k\",\"next_codec\":\"Opus_2ch_48k\",\"audible\":false,\"clock_frames\":%llu,\"first_consumed_frames\":%llu,\"next_consumed_frames\":%llu,\"nonzero_output_frames\":%llu,\"transitions\":%llu,\"transition_start_frame\":%llu,\"transition_end_frame\":%llu,\"underflow_frames\":%llu,\"watchdog_seconds\":6}\n",end.clock_frames,end.first_consumed_frames,end.next_consumed_frames,end.nonzero_output_frames,end.transitions,end.transition_start_frame,end.transition_end_frame,end.underflow_frames);
        return 0;
    }catch(const std::exception &e){if(session)muses_p0_audio_stop(session);std::fprintf(stderr,"ABI test failed: %s\n",e.what());return 1;}
}
