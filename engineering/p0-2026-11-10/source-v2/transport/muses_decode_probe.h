// MIT. P0-only transport/decoder comparison; no output device and no JS PCM.
#pragma once
#include "muses_transport.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    double start_seconds;          // 0 full decode; >0 seek with decoder preroll.
    uint64_t max_output_frames;     // canonical48k stereo; <=48,000*900.
    uint32_t timeout_ms;            // each local/native pass, <=60,000.
} MDProbeLimits;
typedef struct {
    uint64_t output_frames, nonzero_samples;
    double rms, first_output_seconds;
    uint32_t source_sample_rate, source_channels, codec_id;
    int32_t ffmpeg_error;
    char pcm_sha256[65];            // canonical interleaved float48k stereo.
} MDDecodeStats;
typedef struct {
    MDDecodeStats local, native;
    MTStats transport;
    int32_t equal_pcm, error;       //0 success;1 args;2 local;3 native;4 mismatch.
} MDProbeReport;

// Native handle must reference the SAME fixed representation as the complete
// task-owned local file. Exclusive serial handle ownership during this call.
// Use a fresh handle for each full/seek comparison to keep per-handle network
// budget <=16MiB. Caller sets transport RSS guard (root integration <=256MiB).
// Streams PCM through bounded conversion storage into counts/RMS/SHA only.
// Only AAC/Opus are accepted in this P0 dependency build. No sound is emitted.
int md_compare_native_to_file(MTHandle *native_handle, const char *local_file,
                              const MDProbeLimits *limits, MDProbeReport *report);
#ifdef __cplusplus
}
#endif
