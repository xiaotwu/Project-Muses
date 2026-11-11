// MIT. Native-only descriptor-to-handle handoff, used by the isolated prototype.
#pragma once
#include <stdint.h>
#include <time.h>
#include "transport/muses_transport.h"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct { MTHandle *handle; uint64_t total_bytes, descriptor_ns; int error; } SPSource;
static inline uint64_t sp_now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000ull+t.tv_nsec; }
SPSource sp_resolve(const char *bundle, int next, const char *codec);
SPSource sp_local(const char *url, uint64_t length);
void sp_cancel_resolver(void);
#ifdef __cplusplus
}
#endif
