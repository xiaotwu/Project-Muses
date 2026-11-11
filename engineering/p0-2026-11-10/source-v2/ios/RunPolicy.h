// MIT. Small shared policy for the isolated iOS proof, not production code.
#pragma once
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

enum { P0_STOP_NONE, P0_STOP_USER, P0_STOP_RESOURCE, P0_STOP_DEADLINE,
       P0_STOP_NOT_BACKGROUND, P0_STOP_SOURCE, P0_STOP_AUDIO, P0_STOP_STORAGE,
       P0_STOP_TRACE };
enum { P0_NEXT_WAIT, P0_NEXT_CANCELLED, P0_NEXT_ALREADY, P0_NEXT_NOT_BACKGROUND,
       P0_NEXT_CLAIMED };
typedef struct {
    atomic_int stop_reason;
    atomic_bool next_claimed;
    _Atomic(double) audio_started;
} P0RunPolicy;
static inline void p0_policy_init(P0RunPolicy *p) {
    atomic_init(&p->stop_reason, P0_STOP_NONE);
    atomic_init(&p->next_claimed, false);
    atomic_init(&p->audio_started, 0);
}
static inline bool p0_cancel(P0RunPolicy *p, int reason) {
    int expected = P0_STOP_NONE;
    return atomic_compare_exchange_strong(&p->stop_reason, &expected, reason);
}
static inline bool p0_cancelled(P0RunPolicy *p) { return atomic_load(&p->stop_reason) != P0_STOP_NONE; }
static inline int p0_next(P0RunPolicy *p, double now, bool app_background, bool scene_background) {
    if (p0_cancelled(p)) return P0_NEXT_CANCELLED;
    double started = atomic_load(&p->audio_started);
    if (started <= 0 || now < started + 30) return P0_NEXT_WAIT;
    if (atomic_load(&p->next_claimed)) return P0_NEXT_ALREADY;
    if (!app_background || !scene_background) return P0_NEXT_NOT_BACKGROUND;
    bool expected = false;
    return atomic_compare_exchange_strong(&p->next_claimed, &expected, true) ? P0_NEXT_CLAIMED : P0_NEXT_ALREADY;
}
static inline bool p0_storage_admit(uint64_t existing, uint64_t reserve, uint64_t limit) {
    return existing <= limit && reserve <= limit - existing;
}
static inline bool p0_trace_admit(size_t rows, size_t bytes, size_t line_bytes, bool terminal) {
    const size_t max_rows = terminal ? 512 : 504;
    const size_t max_bytes = terminal ? 2*1024*1024 : 2*1024*1024 - 8*4096;
    return line_bytes <= 4096 && rows < max_rows && bytes <= max_bytes && line_bytes <= max_bytes - bytes;
}
