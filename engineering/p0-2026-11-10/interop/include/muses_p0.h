#ifndef MUSES_P0_H
#define MUSES_P0_H
#include <stdint.h>
#include <stddef.h>

/* P0 only. No production ABI freeze is implied by this version. */
#define MUSES_ABI_VERSION 1u
typedef uint64_t MusesHandle;
enum MusesResult {
    MUSES_OK = 0, MUSES_INVALID_HANDLE = 1, MUSES_INVALID_ARGUMENT = 2,
    MUSES_ABI_MISMATCH = 3, MUSES_STALE_GENERATION = 4, MUSES_STORAGE_ERROR = 5,
    MUSES_EVENT_GAP = 6, MUSES_EMPTY = 7, MUSES_LIMIT = 8,
    MUSES_OWNER_BUSY = 9, MUSES_INTERNAL = 10
};
enum MusesCommandKind { MUSES_ENQUEUE = 1, MUSES_SELECT = 2, MUSES_RESOLVED = 3, MUSES_CANCEL = 4 };
enum MusesEventKind { MUSES_ENQUEUED = 1, MUSES_SELECTED = 2, MUSES_READY = 3, MUSES_CANCELLED = 4, MUSES_RECOVERED = 5 };
enum MusesState { MUSES_IDLE = 0, MUSES_RESOLVING = 1, MUSES_RESOLVED_STATE = 2 };

typedef struct {
    uint32_t abi_version, struct_size, kind, reserved;
    uint64_t expected_generation, occurrence_id, media_id;
} MusesCommand;
typedef struct {
    uint32_t abi_version, struct_size, state, reserved;
    uint64_t sequence, generation, occurrence_id, media_id, queue_count;
} MusesSnapshot;
typedef struct {
    uint32_t abi_version, struct_size, kind, reserved;
    uint64_t sequence, generation, occurrence_id, media_id;
} MusesEvent;
typedef struct { uint64_t occurrence_id, media_id, ordinal; } MusesQueueEntry;

/* Inputs are borrowed only for the call. Strings are length-delimited UTF-8.
 * Output pointers must be writable/aligned for their C type. All calls are
 * serialized by the prototype; never call from a real-time audio callback.
 * No callbacks enter Swift/.NET. Fixed-size copies use caller-owned storage.
 * Handles are nonzero, opaque, kind-checked, never reused within the process.
 * Open enforces one engine/process and an OS file lock across processes.
 */
uint32_t muses_abi_version(void);
int32_t muses_open(uint32_t abi, const uint8_t *path, size_t length, MusesHandle *out);
int32_t muses_release(MusesHandle engine);
int32_t muses_command(MusesHandle engine, const MusesCommand *command, uint64_t *generation);
/* Immutable snapshots survive mutations and engine release until released.
 * Caller supplies abi_version + struct_size before read. */
int32_t muses_snapshot_acquire(MusesHandle engine, MusesHandle *out);
int32_t muses_snapshot_read(MusesHandle snapshot, MusesSnapshot *out);
int32_t muses_snapshot_entry(MusesHandle snapshot, uint64_t index, MusesQueueEntry *out);
int32_t muses_snapshot_release(MusesHandle snapshot);
/* Subscribe from a snapshot.sequence. Poll returns EMPTY if caught up, GAP
 * if bounded retention was exceeded; resnapshot then resubscribe on GAP.
 * Engine release invalidates its subscriptions. Unsubscribe is serialized
 * with poll, so after it returns no later call can deliver an event. */
int32_t muses_subscribe(MusesHandle engine, uint64_t after_sequence, MusesHandle *out);
int32_t muses_poll(MusesHandle subscription, MusesEvent *out);
int32_t muses_unsubscribe(MusesHandle subscription);
#endif
