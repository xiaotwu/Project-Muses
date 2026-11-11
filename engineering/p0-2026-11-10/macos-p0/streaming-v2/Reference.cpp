// MIT. Reuses the frozen complete-file comparison decoder in a separate CLI.
// It has no output device and never reads a signed URL.
#include "DecodeProbe.snapshot.cpp"
#include <cstdlib>
int main(int argc,char **argv){
    if(argc!=3)return 64;av_log_set_level(AV_LOG_QUIET);
    MDProbeLimits limits{std::strtod(argv[2],nullptr),48000ull*900,15000};MDDecodeStats result{};
    decode(nullptr,argv[1],limits,result);
    std::printf("{\"gate\":\"offline_reference\",\"start_seconds\":%.8f,\"frames\":%llu,\"codec\":\"%s\",\"pcm_sha256\":\"%s\",\"nonzero_samples\":%llu,\"rms\":%.10f,\"ffmpeg_error\":%d}\n",limits.start_seconds,result.output_frames,avcodec_get_name(AVCodecID(result.codec_id)),result.pcm_sha256,result.nonzero_samples,result.rms,result.ffmpeg_error);
    return result.ffmpeg_error?1:0;
}
