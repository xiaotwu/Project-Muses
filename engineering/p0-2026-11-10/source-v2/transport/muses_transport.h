// MIT. P0 bounded native transport; no media bytes or signed URL logs enter JS.
#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef void MTHandle;
typedef enum {
    MT_OK = 0, MT_EOF = 1, MT_CANCELLED = -1, MT_BAD_DESCRIPTOR = -2,
    MT_KIND_UNSUPPORTED = -3, MT_URL_POLICY = -4, MT_HTTP_FORBIDDEN = -5,
    MT_URL_EXPIRED = -6, MT_AUTH_REQUIRED = -7, MT_RANGE_UNSUPPORTED = -8,
    MT_RANGE_INVALID = -9, MT_CONTENT_CHANGED = -10, MT_RESOURCE_LIMIT = -11,
    MT_NETWORK_ERROR = -12, MT_TIMEOUT = -13, MT_TRUNCATED = -14,
    MT_DESTINATION_ERROR = -15, MT_BUSY = -16, MT_HTTP_STATUS = -17
} MTStatus;
typedef enum { MT_DIRECT = 1, MT_HLS = 2, MT_SABR = 3 } MTKind;
typedef enum {
    MT_RETRY_NONE = 0, MT_RETRY_FRESH_DESCRIPTOR = 1,
    MT_RETRY_NETWORK = 2, MT_RETRY_DIFFERENT_CAPABILITY = 3
} MTRetry;
typedef struct { const char *name; const char *value; } MTHeader;
typedef struct {
    uint32_t abi_version;             // 1
    MTKind kind;                     // HLS/SABR explicitly return unsupported.
    const char *url;                 // copied in native memory only, never logged.
    const MTHeader *headers;         // bounded public headers; no Cookie/Auth.
    uint32_t header_count;
    uint64_t content_length_hint;    // 0 unknown; nonzero is a fixed expected total.
    double expires_unix_seconds;     // 0 unknown; 403 alone does not prove expiry.
} MTDescriptor;
typedef struct {
    uint64_t media_limit_bytes;       // >0, <=16 MiB.
    uint64_t network_limit_bytes;     // >0, <=16 MiB; includes refetches.
    uint32_t block_bytes;             // 4 KiB..256 KiB; one pull block in flight.
    uint32_t maximum_requests;        // 1..512; no automatic retry loop.
    uint32_t request_timeout_ms;      // 100..15000.
    int32_t allow_test_loopback;      // works only in MT_TESTING builds.
    uint64_t process_rss_limit_bytes; // observed guard: >0, <=256 MiB; not an allocator limit.
} MTLimits;
typedef struct {
    uint64_t total_bytes, network_bytes, unique_validated_bytes, delivered_bytes;
    uint64_t buffer_high_bytes, resident_high_bytes;
    uint32_t requests, responses, http_status;
    int32_t status, retry, range_supported, complete_file;
    char sha256[65];                  // only populated for committed full file.
} MTStats;

// Required host policy for every initial and redirect URL; no network is opened
// until it returns nonzero. Keep the existing production source host allowlist.
typedef int (*MTAuthorizeURL)(const char *url, void *context);
// Called synchronously after a validated block is written, on the copying
// thread; blocking it creates backpressure and does not enqueue more requests.
typedef void (*MTProgress)(const MTStats *stats, void *context);

MTHandle *mt_create(const MTDescriptor *descriptor, const MTLimits *limits,
                    MTAuthorizeURL authorize, void *context, MTStatus *status);
// Serial reads; cancellation may be concurrent. Returned bytes are copied to
// caller-owned bounded storage. Seek is represented by the next read offset.
MTStatus mt_read_at(MTHandle *handle, uint64_t offset, void *output,
                    size_t capacity, size_t *received);
// The destination must not exist. Writes a mode0600 owned .partial then commits
// atomically only when every [0,total) byte is validated. Failure keeps partial
// evidence; it is never named as a complete file. Owner later cleans it safely.
MTStatus mt_copy_to_file(MTHandle *handle, const char *destination,
                         MTProgress progress, void *context);
void mt_cancel(MTHandle *handle);
MTStatus mt_snapshot(MTHandle *handle, MTStats *stats);
// No concurrent read/copy/snapshot at destruction. Cancel then join your worker.
void mt_destroy(MTHandle *handle);
const char *mt_status_name(MTStatus status); // fixed redacted names, no raw error.
#ifdef __cplusplus
}
#endif
