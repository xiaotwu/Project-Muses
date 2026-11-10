// MIT. Included after baseline host helpers, before RunProof.
#include "transport/muses_transport.h"
#ifndef P0_IOS
#include "transport/muses_decode_probe.h"
#endif
#include "parser/p0_parser.h"
static NSString *V2Client = @"VISIONOS";
static NSString *V2Codec = @"aac";
static NSDictionary *V2Descriptor;
static NSString *V2CompletedPath;
static NSString *V2SHA(const void *bytes, size_t length) {
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(bytes, (CC_LONG)length, digest);
    NSMutableString *value = [NSMutableString stringWithCapacity:64];
    for (int i=0;i<CC_SHA256_DIGEST_LENGTH;i++) [value appendFormat:@"%02x",digest[i]];
    return value;
}

static BOOL V2MediaAllowed(NSURL *url) {
    NSString *host = url.host.lowercaseString;
    return [url.scheme isEqual:@"https"] &&
        ([host isEqual:@"googlevideo.com"] || [host hasSuffix:@".googlevideo.com"] ||
         [host isEqual:@"youtube.com"] || [host hasSuffix:@".youtube.com"]);
}
static JSValue V2ReceiveDescriptor(JSContext *ctx, JSValueConst obj, int argc, JSValueConst *argv) {
    if (argc != 1) return JS_ThrowTypeError(ctx, "descriptor argument count");
    NSString *serialized = String(ctx, argv[0]);
    NSData *json = [serialized dataUsingEncoding:NSUTF8StringEncoding];
    if (json.length > 32768) return JS_ThrowRangeError(ctx, "descriptor limit");
    NSDictionary *value = [NSJSONSerialization JSONObjectWithData:json options:0 error:nil];
    NSString *expectedVideo = [activeMode hasSuffix:@"_next"] ? @"eRsGyueVLvQ" : @"aqz-KE-bpKQ";
    if (![value isKindOfClass:NSDictionary.class] || [value[@"version"] integerValue] != 1 ||
        ![value[@"kind"] isEqual:@"direct"] || ![value[@"client"] isEqual:V2Client] ||
        ![value[@"codec"] isEqual:V2Codec] ||
        ![value[@"video_id"] isEqual:expectedVideo] ||
        ![value[@"url"] isKindOfClass:NSString.class] || !V2MediaAllowed([NSURL URLWithString:value[@"url"]]) ||
        ![value[@"content_length"] isKindOfClass:NSNumber.class] ||
        [value[@"content_length"] unsignedLongLongValue] == 0 || [value[@"content_length"] unsignedLongLongValue] > 16*1024*1024)
        return JS_ThrowTypeError(ctx, "invalid native descriptor");
    V2Descriptor = [value copy];
    return JS_UNDEFINED;
}
static int V2ParserCancelled(void *ignored) { return V2ShouldStop(); }
static NSDictionary *V2FilterEvent(NSDictionary *event) {
    NSDictionary *meta = event[@"meta"];
    NSURL *url = [NSURL URLWithString:meta[@"url"]];
    if ([meta[@"status"] integerValue] != 200 || ![url.path containsString:@"/s/player/"] || ![url.path hasSuffix:@"/base.js"])
        return event;
    NSData *input = event[@"body"];
    size_t capacity = 256*1024;
    char *reduced = malloc(capacity+1);
    if (!reduced) return nil;
    struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
    p0_parser_limits limits = {4*1024*1024, 64*1024*1024, capacity, 256,
        (uint64_t)now.tv_sec*1000000000+now.tv_nsec+5000000000ull, NULL};
    limits.should_cancel = V2ParserCancelled;
    p0_parser_result result = {0};
    p0_parser_status status = p0_player_reduce(input.bytes, input.length, &limits, reduced, capacity+1, &result);
    Output(JSONString(@{@"gate":@"native_player_reduce", @"outcome":status==P0_PARSE_OK?@"pass":@"fail",
        @"category":@(p0_parser_status_name(status)), @"input_bytes":@(input.length), @"output_bytes":@(result.output_bytes),
        @"player_sha256":V2SHA(input.bytes,input.length),
        @"reduced_sha256":status==P0_PARSE_OK?V2SHA(reduced,result.output_bytes):@"",
        @"native_peak_bytes":@(result.peak_working_bytes), @"native_live_after_bytes":@(result.live_working_bytes),
        @"parse_ms":@(result.parse_ns/1e6), @"reduce_ms":@(result.reduce_ns/1e6),
        @"solver_matches":@(result.solver_matches), @"timestamp_matches":@(result.timestamp_matches)}));
    if (status != P0_PARSE_OK) { free(reduced); return nil; }
    NSMutableDictionary *replaced = [event mutableCopy];
    replaced[@"body"] = [NSData dataWithBytesNoCopy:reduced length:result.output_bytes freeWhenDone:YES];
    NSMutableDictionary *newMeta = [meta mutableCopy], *headers = [meta[@"headers"] mutableCopy];
    headers[@"content-length"] = @(result.output_bytes).stringValue;
    newMeta[@"headers"] = headers; replaced[@"meta"] = newMeta;
    return replaced;
}
static int V2Authorize(const char *url, void *ignored) {
    return V2MediaAllowed([NSURL URLWithString:@(url)]);
}
static void V2Progress(const MTStats *stats, void *ignored) {
    // Bounded per-block counts only. No URL or response headers are retained.
    Output(JSONString(@{@"gate":@"native_media_progress", @"outcome":@"pass",
        @"validated_bytes":@(stats->unique_validated_bytes), @"total_bytes":@(stats->total_bytes),
        @"requests":@(stats->requests), @"buffer_high_bytes":@(stats->buffer_high_bytes)}));
}
static int V2Transfer(void) {
    if (V2ShouldStop()) return 130;
    NSDictionary *availability = V2Descriptor[@"availability"];
    if (![availability isKindOfClass:NSDictionary.class] || ![availability[@"state"] isEqual:@"known"] ||
        ![availability[@"availableAtUnixMs"] isKindOfClass:NSNumber.class] ||
        !isfinite([availability[@"availableAtUnixMs"] doubleValue])) return 2;
    double wait = MAX(0, [availability[@"availableAtUnixMs"] doubleValue]/1000.0 - NSDate.date.timeIntervalSince1970);
    if (wait > 20) {
        Output(JSONString(@{@"gate":@"native_availability", @"outcome":@"bounded_stop", @"wait_ms":@((int)(wait*1000))}));
        return 2;
    }
    double available = Now() + wait;
    while (Now() < available) {
        if (V2ShouldStop()) return 130;
        [NSThread sleepForTimeInterval:MIN(0.02, available-Now())];
    }
    NSDictionary *publicHeaders = V2Descriptor[@"headers"];
    if (![publicHeaders isKindOfClass:NSDictionary.class] || publicHeaders.count > 8) return 2;
    MTHeader headers[8]; uint32_t count = 0;
    for (NSString *name in publicHeaders) {
        if (![publicHeaders[name] isKindOfClass:NSString.class]) return 2;
        headers[count++] = (MTHeader){name.UTF8String, [publicHeaders[name] UTF8String]};
    }
    MTDescriptor descriptor = {1, MT_DIRECT, [V2Descriptor[@"url"] UTF8String], headers, count,
        [V2Descriptor[@"content_length"] unsignedLongLongValue], [V2Descriptor[@"expires_unix_seconds"] doubleValue]};
    MTLimits limits = {16*1024*1024, 16*1024*1024, 256*1024, 512, 15000, 0, 256*1024*1024};
    MTStatus status;
    MTHandle *handle = mt_create(&descriptor, &limits, V2Authorize, NULL, &status);
    if (!handle) {
        Output(JSONString(@{@"gate":@"native_media_create", @"outcome":@"fail", @"category":@(mt_status_name(status))}));
        return 1;
    }
    NSString *name = [NSString stringWithFormat:@"%@-%@-%@.%@", V2Client, V2Descriptor[@"video_id"], NSUUID.UUID.UUIDString,
        [V2Codec isEqual:@"opus"] ? @"webm" : @"m4a"];
    NSString *directory = mediaDirectory ?: @"/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/media";
    NSString *destination = [directory stringByAppendingPathComponent:name];
    double before = Now();
    V2BindTransfer(handle);
    status = mt_copy_to_file(handle, destination.fileSystemRepresentation, V2Progress, NULL);
    MTStats stats; mt_snapshot(handle, &stats); V2UnbindTransfer(handle); mt_destroy(handle);
    struct rusage usage; getrusage(RUSAGE_SELF, &usage);
    Output(JSONString(@{@"gate":@"native_media_complete", @"outcome":status==MT_OK?@"pass":@"fail",
        @"category":@(mt_status_name(status)), @"http_status":@(stats.http_status),
        @"expected_bytes":@(descriptor.content_length_hint), @"validated_bytes":@(stats.unique_validated_bytes),
        @"network_bytes":@(stats.network_bytes), @"requests":@(stats.requests),
        @"complete_file":@(stats.complete_file), @"sha256":@(stats.sha256),
        @"buffer_high_bytes":@(stats.buffer_high_bytes), @"process_maxrss_bytes":@(usage.ru_maxrss),
        @"elapsed_ms":@((Now()-before)*1000), @"owned_media_filename":name}));
    if (status != MT_OK || !stats.complete_file) return 1;
    V2CompletedPath = destination;
#ifdef P0_IOS
    NSError *protectionError = nil;
    if (![[NSFileManager defaultManager] setAttributes:@{NSFileProtectionKey:NSFileProtectionCompleteUntilFirstUserAuthentication}
        ofItemAtPath:destination error:&protectionError]) {
        Output(JSONString(@{@"gate":@"native_media_protection", @"outcome":@"fail", @"error_code":@(protectionError.code)}));
        return 1;
    }
#else
    // Each comparison gets a fresh, independently bounded handle to the exact
    // same representation. No descriptor refresh or source substitution here.
    for (int pass = 0; pass < 2; pass++) {
        MTHandle *decodeHandle = mt_create(&descriptor, &limits, V2Authorize, NULL, &status);
        if (!decodeHandle) return 1;
        V2BindTransfer(decodeHandle);
        MDProbeLimits decodeLimits = {pass == 0 ? 0 : 30, 48000ull*900, 60000};
        MDProbeReport report = {0};
        before = Now();
        int error = md_compare_native_to_file(decodeHandle, destination.fileSystemRepresentation, &decodeLimits, &report);
        V2UnbindTransfer(decodeHandle); mt_destroy(decodeHandle);
        getrusage(RUSAGE_SELF, &usage);
        Output(JSONString(@{@"gate":pass == 0 ? @"native_decode_full" : @"native_decode_seek_30s",
            @"outcome":error == 0 ? @"pass" : @"fail", @"error":@(error),
            @"transport_category":@(mt_status_name(report.transport.status)), @"http_status":@(report.transport.http_status),
            @"local_error":@(report.local.ffmpeg_error), @"native_error":@(report.native.ffmpeg_error),
            @"equal_pcm":@(report.equal_pcm), @"local_frames":@(report.local.output_frames),
            @"native_frames":@(report.native.output_frames), @"nonzero_samples":@(report.native.nonzero_samples),
            @"rms":@(report.native.rms), @"pcm_sha256":@(report.native.pcm_sha256),
            @"first_output_seconds":@(report.native.first_output_seconds),
            @"source_sample_rate":@(report.native.source_sample_rate), @"source_channels":@(report.native.source_channels),
            @"network_bytes":@(report.transport.network_bytes), @"requests":@(report.transport.requests),
            @"buffer_high_bytes":@(report.transport.buffer_high_bytes), @"process_maxrss_bytes":@(usage.ru_maxrss),
            @"elapsed_ms":@((Now()-before)*1000)}));
        if (error != 0) return 1;
    }
#endif
    return 0;
}

int P0V2RunSource(NSString *bundle, BOOL next) {
    if (!P0V2BeginOperation(45)) return 75;
    @autoreleasepool {
        V2Client = @"TV_SAMSUNG"; V2Codec = @"aac";
        V2Descriptor = nil; V2CompletedPath = nil;
        extern int RunProof(NSString *, NSString *);
        int status = RunProof(bundle, next ? @"resolve_next" : @"resolve_first");
        if (status == 0 && !V2Descriptor) status = 1;
        if (status == 0) status = V2Transfer();
        if (V2ShouldStop()) status = 130;
        Output(JSONString(@{@"gate":@"source_operation", @"outcome":status == 0 ? @"pass" : @"fail",
            @"code":@(status), @"reason":V2StopReason(), @"observed_peak_rss_bytes":@(V2ObservedPeakRSS()),
            @"deadline_seconds":@45, @"next":@(next)}));
        NSString *path = status == 0 ? V2CompletedPath : nil;
        V2Descriptor = nil; V2CompletedPath = nil;
        P0V2EndOperation();
        if (path && mediaHandler) mediaHandler(path, next);
        return status;
    }
}

#ifndef P0_IOS
int main(int argc, char **argv) {
    @autoreleasepool {
        if (argc < 3 || argc > 5) return 64;
        NSString *mode = @(argv[2]);
        if (![@[@"capabilities", @"resolve_first", @"resolve_next", @"direct_first", @"direct_next"] containsObject:mode]) return 64;
        if (argc > 3) V2Client = @(argv[3]);
        if (argc > 4) V2Codec = @(argv[4]);
        if (![@[@"IOS", @"VISIONOS", @"TV", @"TV_SAMSUNG", @"WEB", @"WEB_EMBEDDED"] containsObject:V2Client] ||
            ![@[@"aac", @"opus"] containsObject:V2Codec]) return 64;
        extern int RunProof(NSString *, NSString *);
        if (!P0V2BeginOperation(180)) return 75;
        int status = RunProof(@(argv[1]), mode);
        // Metadata/parser runtime is disposed before native media transfer.
        if (status == 0 && ![mode isEqual:@"capabilities"] && !V2Descriptor) status = 1;
        if (status == 0 && V2Descriptor) status = V2Transfer();
        if (V2ShouldStop()) status = 130;
        Output(JSONString(@{@"gate":@"source_operation", @"outcome":status == 0 ? @"pass" : @"fail",
            @"code":@(status), @"reason":V2StopReason(), @"observed_peak_rss_bytes":@(V2ObservedPeakRSS())}));
        V2Descriptor = nil; V2CompletedPath = nil;
        P0V2EndOperation();
        return status;
    }
}
#endif
