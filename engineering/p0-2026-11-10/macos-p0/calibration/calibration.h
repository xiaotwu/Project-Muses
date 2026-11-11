// SPDX-License-Identifier: MIT
#ifndef MUSES_P0_CALIBRATION_H
#define MUSES_P0_CALIBRATION_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>

#define CAL_VERSION "acoustic-chain-v1"
#define CAL_MAX_SECONDS 8.0
#define CAL_AUDIO_BYTES (8u*1024u*1024u)
#define CAL_ANALYSIS_RATE 6000.0
#define CAL_MARKER_SECONDS .160
#define CAL_MARKER_GAP_SECONDS 2.5
#define CAL_MAX_ANCHORS 4096

typedef enum { CAL_IDLE, CAL_PERMISSION, CAL_RUNNING, CAL_CANCELLED, CAL_FINISHING } CalState;
typedef struct { _Atomic uint64_t packed; } CalGate;
void cal_gate_init(CalGate *gate);
uint64_t cal_gate_begin(CalGate *gate);
bool cal_gate_start(CalGate *gate,uint64_t generation);
bool cal_gate_cancel(CalGate *gate);
bool cal_gate_cancel_generation(CalGate *gate,uint64_t generation);
bool cal_gate_finish(CalGate *gate,uint64_t generation);
bool cal_gate_reset(CalGate *gate,uint64_t generation);
bool cal_gate_running(const CalGate *gate,uint64_t generation);
bool cal_gate_finishing(const CalGate *gate,uint64_t generation);
bool cal_gate_commit_result(CalGate *gate,uint64_t generation);

typedef struct { uint64_t frame,host_ns; } CalAnchor;
typedef struct {
    const float *samples;
    size_t count;
    double sample_rate;
    const CalAnchor *anchors;
    size_t anchor_count;
    bool (*should_cancel)(void *opaque);
    void *cancel_opaque;
} CalCapture;
typedef struct {
    double reference_frame,onset_frame,correlation,runner_up_correlation,signal_rms;
    uint64_t reference_host_ns,onset_host_ns;
} CalMatch;
typedef struct {
    bool valid;
    const char *reason;
    CalMatch markers[2];
    double noise_rms,clipped_fraction,clock_drift_ppm,clock_max_residual_ms;
    double detector_error_bound_ms;
    size_t working_audio_bytes;
    const char *confidence; // A deterministic match class, never a probability.
} CalResult;

// Generates original finite nonperiodic waveforms. No media source is used.
bool cal_make_marker(unsigned marker,double rate,float *output,size_t frames);
void cal_wipe(void *bytes,size_t count);
// Does not own input, persist PCM, access devices, or allocate > the audio cap.
CalResult cal_analyze(const CalCapture *capture);
#endif
