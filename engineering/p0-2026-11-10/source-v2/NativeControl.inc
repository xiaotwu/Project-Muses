// SPDX-License-Identifier: MIT
// Included once in the Objective-C native host, after its system includes.
#ifndef P0_V2_NATIVE_CONTROL_INCLUDED
#define P0_V2_NATIVE_CONTROL_INCLUDED
#import <Foundation/Foundation.h>
#include <mach/mach.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <time.h>
#include "transport/muses_transport.h"

enum { V2_REASON_NONE=0, V2_REASON_CANCELLED=1, V2_REASON_DEADLINE=2,
       V2_REASON_RSS=3, V2_REASON_RSS_UNAVAILABLE=4,
       V2_REASON_WATCHDOG_UNAVAILABLE=5, V2_REASON_TRANSFER_BINDING=6 };
enum { V2_CONTROL_IDLE=0, V2_CONTROL_RUNNING=1, V2_CONTROL_ENDING=2 };
static const uint64_t V2_RSS_LIMIT = 256ull * 1024 * 1024;
static const uint64_t V2_SAMPLE_NS = 100000000ull;
static pthread_mutex_t V2ControlMutex = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t V2ControlWake = PTHREAD_COND_INITIALIZER;
static int V2ControlPhase;
static uint64_t V2LastGeneration, V2WatchGeneration;
static pthread_t V2WatchThread;
static bool V2WatchCreated, V2TransferCancelled;
static MTHandle *V2CurrentTransfer;
static _Atomic(uint64_t) V2ActiveGeneration, V2DeadlineNS, V2NextRSSNS, V2PeakRSS;
static atomic_int V2Reason;
static _Thread_local uint64_t V2OwnerGeneration;

#ifdef P0_V2_CONTROL_TESTING
// Deterministic local harness only; production always uses Mach/monotonic time.
static uint64_t P0V2TestNowNS(void);
static bool P0V2TestReadRSS(uint64_t *bytes);
#endif
static uint64_t P0V2ClockNS(void) {
#ifdef P0_V2_CONTROL_TESTING
    return P0V2TestNowNS();
#else
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return UINT64_MAX;
    return (uint64_t)value.tv_sec * 1000000000ull + (uint64_t)value.tv_nsec;
#endif
}
static bool P0V2ReadRSS(uint64_t *bytes) {
#ifdef P0_V2_CONTROL_TESTING
    return P0V2TestReadRSS(bytes);
#else
    mach_task_basic_info_data_t info;
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return false;
    *bytes = info.resident_size;
    return true;
#endif
}
static void P0V2SetStop(int reason) {
    int none = V2_REASON_NONE;
    atomic_compare_exchange_strong(&V2Reason, &none, reason);
    // Signaling without the mutex is safe: the watcher also has a 100 ms poll.
    // Never enter transport here; this path can run inside a parser/JS callback.
    pthread_cond_signal(&V2ControlWake);
}
static void P0V2Observe(uint64_t generation, bool forceRSS) {
    if (!generation || atomic_load(&V2ActiveGeneration) != generation) return;
    uint64_t now = P0V2ClockNS();
    if (now >= atomic_load(&V2DeadlineNS)) P0V2SetStop(V2_REASON_DEADLINE);
    uint64_t due = atomic_load(&V2NextRSSNS);
    if (forceRSS || (now >= due && atomic_compare_exchange_strong(&V2NextRSSNS, &due, now + V2_SAMPLE_NS))) {
        uint64_t bytes = 0;
        if (!P0V2ReadRSS(&bytes)) P0V2SetStop(V2_REASON_RSS_UNAVAILABLE);
        else {
            uint64_t old = atomic_load(&V2PeakRSS);
            while (bytes > old && !atomic_compare_exchange_weak(&V2PeakRSS, &old, bytes)) {}
            if (bytes > V2_RSS_LIMIT) P0V2SetStop(V2_REASON_RSS);
        }
    }
}
// The caller holds V2ControlMutex through mt_cancel. Therefore unbind cannot
// return while either UI cancellation or the watcher still uses this handle.
static void P0V2CancelBoundLocked(void) {
    if (V2CurrentTransfer && !V2TransferCancelled) {
        V2TransferCancelled = true;
        mt_cancel(V2CurrentTransfer);
    }
}
static void *P0V2Watch(void *argument) {
    @autoreleasepool {
        uint64_t generation = *(const uint64_t *)argument;
        pthread_mutex_lock(&V2ControlMutex);
        while (V2ControlPhase == V2_CONTROL_RUNNING && atomic_load(&V2ActiveGeneration) == generation) {
            P0V2Observe(generation, true);
            if (atomic_load(&V2Reason) != V2_REASON_NONE) {
                P0V2CancelBoundLocked();
                break;
            }
            struct timespec relative = {0, (long)V2_SAMPLE_NS};
            pthread_cond_timedwait_relative_np(&V2ControlWake, &V2ControlMutex, &relative);
        }
        pthread_mutex_unlock(&V2ControlMutex);
    }
    return NULL;
}

// Begin/End/Bind/Unbind/ShouldStop run on one serial operation worker. UI calls
// Cancel only. A false Begin (BUSY or invalid timeout) never resets active work.
bool P0V2BeginOperation(double seconds) {
    if (!isfinite(seconds) || seconds <= 0 || seconds > 180) return false;
    uint64_t now = P0V2ClockNS(), duration = (uint64_t)(seconds * 1e9);
    if (!duration || now > UINT64_MAX - duration - V2_SAMPLE_NS) return false;
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase != V2_CONTROL_IDLE) { pthread_mutex_unlock(&V2ControlMutex); return false; }
    uint64_t generation = ++V2LastGeneration;
    if (!generation) generation = ++V2LastGeneration;
    V2ControlPhase = V2_CONTROL_RUNNING;
    V2WatchGeneration = generation;
    V2CurrentTransfer = NULL;
    V2TransferCancelled = false;
    atomic_store(&V2Reason, V2_REASON_NONE);
    atomic_store(&V2PeakRSS, 0);
    atomic_store(&V2DeadlineNS, now + duration);
    atomic_store(&V2NextRSSNS, now + V2_SAMPLE_NS);
    atomic_store(&V2ActiveGeneration, generation);
    V2OwnerGeneration = generation;
    P0V2Observe(generation, true);
    int error = pthread_create(&V2WatchThread, NULL, P0V2Watch, &V2WatchGeneration);
    V2WatchCreated = error == 0;
    if (error) {
        P0V2SetStop(V2_REASON_WATCHDOG_UNAVAILABLE);
        atomic_store(&V2ActiveGeneration, 0);
        V2OwnerGeneration = 0;
        V2ControlPhase = V2_CONTROL_IDLE;
    }
    pthread_mutex_unlock(&V2ControlMutex);
    return !error;
}
void P0V2Cancel(void) {
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase == V2_CONTROL_RUNNING) {
        P0V2SetStop(V2_REASON_CANCELLED);
        P0V2CancelBoundLocked();
    }
    pthread_mutex_unlock(&V2ControlMutex);
}
int V2ShouldStop(void) {
    uint64_t generation = V2OwnerGeneration;
    if (!generation || atomic_load(&V2ActiveGeneration) != generation) return 1;
    P0V2Observe(generation, false);
    return atomic_load(&V2Reason) != V2_REASON_NONE;
}
void V2BindTransfer(MTHandle *handle) {
    if (!handle) return;
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase != V2_CONTROL_RUNNING || !V2OwnerGeneration || atomic_load(&V2ActiveGeneration) != V2OwnerGeneration) {
        mt_cancel(handle); // Fail closed; never attach a stale worker's handle.
    } else if (V2CurrentTransfer && V2CurrentTransfer != handle) {
        P0V2SetStop(V2_REASON_TRANSFER_BINDING);
        P0V2CancelBoundLocked();
        mt_cancel(handle);
    } else {
        V2CurrentTransfer = handle;
        if (atomic_load(&V2Reason) != V2_REASON_NONE) P0V2CancelBoundLocked();
    }
    pthread_mutex_unlock(&V2ControlMutex);
}
void V2UnbindTransfer(MTHandle *handle) {
    pthread_mutex_lock(&V2ControlMutex);
    if (V2OwnerGeneration && atomic_load(&V2ActiveGeneration) == V2OwnerGeneration && V2CurrentTransfer == handle) {
        V2CurrentTransfer = NULL;
        V2TransferCancelled = false;
    }
    pthread_mutex_unlock(&V2ControlMutex);
}
void P0V2EndOperation(void) {
    pthread_mutex_lock(&V2ControlMutex);
    if (V2ControlPhase != V2_CONTROL_RUNNING || !V2OwnerGeneration || atomic_load(&V2ActiveGeneration) != V2OwnerGeneration) {
        pthread_mutex_unlock(&V2ControlMutex);
        return;
    }
    V2ControlPhase = V2_CONTROL_ENDING;
    atomic_store(&V2ActiveGeneration, 0);
    // Defensive cancellation; the owner must still join media work before
    // destroying any handle. End never destroys a caller-owned transport.
    P0V2CancelBoundLocked();
    V2CurrentTransfer = NULL;
    V2TransferCancelled = false;
    pthread_cond_signal(&V2ControlWake);
    bool join = V2WatchCreated;
    pthread_t thread = V2WatchThread;
    pthread_mutex_unlock(&V2ControlMutex);
    if (join) pthread_join(thread, NULL);
    pthread_mutex_lock(&V2ControlMutex);
    V2WatchCreated = false;
    V2ControlPhase = V2_CONTROL_IDLE;
    V2OwnerGeneration = 0;
    pthread_mutex_unlock(&V2ControlMutex);
}
NSString *V2StopReason(void) {
    switch (atomic_load(&V2Reason)) {
        case V2_REASON_NONE: return @"none";
        case V2_REASON_CANCELLED: return @"cancelled";
        case V2_REASON_DEADLINE: return @"deadline";
        case V2_REASON_RSS: return @"rss_limit";
        case V2_REASON_RSS_UNAVAILABLE: return @"rss_observer_unavailable";
        case V2_REASON_WATCHDOG_UNAVAILABLE: return @"watchdog_unavailable";
        case V2_REASON_TRANSFER_BINDING: return @"transfer_binding";
        default: return @"unknown";
    }
}
uint64_t V2ObservedPeakRSS(void) { return atomic_load(&V2PeakRSS); }
#endif
