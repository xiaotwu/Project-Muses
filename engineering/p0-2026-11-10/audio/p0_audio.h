// MIT. P0-only ABI; all control calls run off the UI/audio thread.
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint64_t clock_frames, callbacks, underflow_frames, clipped_samples;
    uint64_t transition_start_frame, transition_end_frame, transitions;
    uint64_t first_decoded_frames, next_decoded_frames;
    uint64_t first_buffered_frames, next_buffered_frames;
    uint64_t starts, stops, reroutes, interruptions;
    int32_t first_error, next_error, next_ready, timed_stop;
    uint64_t first_consumed_frames, next_consumed_frames, nonzero_output_frames;
} MusesP0AudioSnapshot;

// Host sets AVAudioSession category/activation; the bridge never changes it.
// first_path is a complete bounded task-owned AAC/M4A or Opus/WebM file.
// max_seconds in [2,180]; audible=0 produces silence, audible=1 uses 0.12 app gain.
// Successful session has exactly one shared native output. Error codes are
// implementation-local negative integers; nullptr means no active session.
void *muses_p0_audio_start(const char *first_path, int max_seconds, int audible, int *error);

// Exactly one next item per P0 session. Call only after a fresh resolution and
// complete bounded download. This creates/decodes the second input only now.
// Transition is scheduled from the observed output clock AFTER preparation.
// lead_ms in [100,10000], fade_ms in [0,5000]. No system route/volume mutation.
int muses_p0_audio_prepare_next(void *session, const char *next_path, int lead_ms, int fade_ms);
int muses_p0_audio_snapshot(void *session, MusesP0AudioSnapshot *out);

// Serial control ownership: no concurrent prepare_next/stop. Snapshot may run
// during prepare_next, but must not overlap stop/destruction. Always call stop.
void muses_p0_audio_stop(void *session);
int muses_p0_audio_test(const char *aac_path, const char *opus_path, int device);
#ifdef __cplusplus
}
#endif
