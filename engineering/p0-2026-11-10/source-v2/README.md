# P0 source continuation

Status: in progress. Cold bounded parsing and complete AAC/Opus delivery now
work on the tested macOS samples. P0 and [XW-145](https://linear.app/xiaotwu/issue/XW-145/p0-来源门槛完整媒体传输与解析内存方案)
are not complete: the corrected physical iPhone proof and broader P0 corpus,
baseline and distribution work have separate gates. The original `source/` failure evidence at
`b16bc3066726d84974e8317246de6b60aff41207` remains unchanged.

This is an isolated engineering prototype, not the new application backend or
a release. The approved Rust Core/native UI architecture and full P0–P9 scope
remain intact. No production repository, user library, installed production app,
Pages content, or release asset is changed by this continuation.

## What changed

1. Public metadata uses an ephemeral native HTTP bridge. An authentic anonymous
   server bootstrap replaces the generated local visitor context; no user login,
   Cookie, token, remote resolver, or desktop subprocess is used by the native
   executable. The tested public Samsung request profile stays internally
   consistent, including its version during n/signature solving.
2. [Native syntax windows](parser/README.md) reduce the public player before it
   enters the unchanged pinned YouTube.js extractor. Tree-sitter and its JS
   grammar retain their MIT licenses. The full player, reduced dependencies and
   reference solver are pinned by SHA; only bounded receipts are committed.
3. QuickJS keeps its **64 MiB** main heap. Dynamic n/signature code executes in a
   separate **8 MiB / one-second** runtime with no network bindings. The reduced
   extractor produces the same solver bytes as the full-player reference. The
   [QuickJS-NG comparison](runtime/README.md) does not justify an engine change;
   the original runtime remains selected for this proof.
4. JS returns a small typed descriptor. [Native transport](transport/README.md)
   owns URLs and media bytes: a 256 KiB pull buffer, validated ranges, a private
   partial file and an atomic completion. It never fills a JS media ArrayBuffer.
5. [Operation control](control/README.md) enforces cancellation and deadlines
   across metadata, native parsing, isolated evaluation and transfer. A native
   watchdog samples RSS every 100 ms against **256 MiB**; this is an observation
   limit, not a hard whole-process allocator ceiling. Event/timer dispatch and
   microtask draining check the same stop state, including a 128-job tick limit.
6. [NativeInput.inc](NativeInput.inc) supplies QuickJS's required trailing NUL
   at both script-evaluation boundaries. It copies at most 4 MiB into an owned
   `length + 1` buffer, appends the terminator, and frees the copy after evaluation.
   `NSData.bytes` does not promise this terminator. Nil, oversized and allocation
   failures return explicit script errors. The bundled source is also counted
   and hashed before evaluation without logging its contents.

## Verified desktop results

| Check | Result and evidence |
| --- | --- |
| Cold parser | 2,658,728-byte player → 189,450-byte reduced program; native peak about 7.4 MB, zero retained native allocations; 139 lifecycle checks. [Report](parser/README.md) |
| First AAC, Big Buck Bunny | Complete 15,479,228 bytes / 60 requests. Full decode 30,466,048 stereo frames; 30-second seek 29,026,048 frames. Both native-network PCM hashes equal same-file decode. Highest observed RSS 85,278,720 bytes. [Receipt](evidence/20261110T221805.376129Z-resolve_first-TV_SAMSUNG-aac.json) |
| First Opus, same recording | Complete 10,258,925 bytes / 40 requests. Full decode 30,459,751 frames; seek 29,019,775 frames. PCM comparisons match. Highest recorded native RSS 81,084,416 bytes. [Receipt](evidence/20261110T221824.869768Z-resolve_first-TV_SAMSUNG-opus.json) |
| Fresh second recording, Sintel | Honored a declared five-second preroll wait, then 14,373,564 bytes / 55 requests. Full 42,628,493 frames; seek 41,188,493 frames; both native/local PCM hashes match. Highest recorded RSS 82,264,064 bytes. [Receipt](evidence/20261110T224616.589418Z-resolve_next-TV_SAMSUNG-aac.json) |
| Real-time audio bridge | Real six-channel AAC → stereo Opus with the existing native bridge, muted six-second output: one transition, zero observed underflows, native timed stop. This is not an audibility claim. [Evidence](ios/README.md) |
| Resource/failure boundaries | 122 control checks and 42 actual generated-host checks: microtask deadline, timer ceiling, isolated-loop deadline/cancel, native-parser cancellation, then fresh successful operations. [Evidence](control/README.md) |
| Initial IOS public profile | Four 256 KiB blocks then HTTP 403; no completed file, about 35.8 MB RSS. This remains a real failure; the Samsung success does not establish its cause. [Receipt](evidence/20261110T215502.611531Z-direct_first-IOS-aac.json) |

The decoder comparison proves that two byte-delivery paths agree using the
same pinned decoder. It is not independent decoding ground truth or a universal
seek-accuracy claim. The previous Opus EOF warning remains recorded in the
original audio evidence. Direct transport is implemented; HLS/SABR are explicit
unsupported capabilities here, not guessed URLs or silent alternate sources.

The second sample, Sintel, exposed a 97,203-character ad `playerVars` field.
[Availability parsing](availability.md) now uses a separate 128 KiB byte bound
and scans query pairs without copying/decoding large irrelevant values. Its
64-pair and short-value limits remain. The public player identifies the observed
`MILLISECONDS` placement as a content-offset midroll; only a strictly positive
start and valid end interval exclude it from initial preroll waiting. Malformed
or unknown timing still stops before any media request. All 115 availability
fixtures pass. No raw ad payload, signed URL or visitor value is retained.

The live player changed during testing: the final second-recording run used
2,661,557 input bytes (SHA `dffc617520e77f921ec91cb79d975454f96f97f9620e48c99f4c7a623b948251`)
and 190,486 reduced bytes, with a 7,384,931-byte native peak. This is an additional
successful live observation, not the same frozen input used in the 139 lifecycle
checks or a substitute for the planned multi-version sample corpus.

## Physical-device candidate

The [new iOS controller](ios/README.md) uses complete real media and the native
audio bridge. The second item is not resolved beforehand: at audio +30 seconds,
both UIApplication and UIScene must report background before it starts a fresh
operation. All lifecycle values are read on the main thread, with their sample
time retained separately from the event time. Remote early-next is disabled.

The probe stops at audio +90 seconds. Native audio has its own watchdog, source
operations have 45-second limits, and cancellation invalidates stale callbacks.
The app's owned media budget is 32 MiB per run and its whole v2 cache is capped
at 64 MiB, with 34 MiB admission reservation including a bounded trace. A full
cache refuses another run and retains prior evidence; it does not silently
delete it. It never scans or modifies the user's music library.

Root added an iOS-specific creation branch to the transport after the original
transport slice was frozen: the partial file is created without overwrite and
with `NSFileProtectionCompleteUntilFirstUserAuthentication` before writing, its
class is checked, and the completed file is checked again. This avoids relying
on assumed directory-protection inheritance. The original slice manifest is a
historical snapshot; the final integration manifest records this delta. Actual
locked-device read/write behavior still needs physical verification.

### Candidate 5 result and input-boundary repair

The [locked trace](evidence/phone-candidate-5/locked-trace.jsonl) and
[summary](evidence/phone-candidate-5/locked-summary.json) confirm real background
state on the main thread: both application and scene were background and
protected data became unavailable. The user reported continuous audible first
media while locked, but could not identify the transition or reason for stop.
No device queries or debugger connection occurred during the measurement window.

At audio +30.0256 seconds a fresh second operation began. It failed about 66 ms
later during bundle evaluation, before any HTTP request. Audio stopped with
`source_failure` at about +30.12 seconds, with zero transitions, zero second-input
consumption and `timed_stop = 0`. This was **not** the intended 90-second stop and
is not a background-next pass. Peak process RSS was 99,057,664 bytes, below the
observation ceiling. The prior foreground-only run and denied locked launch are
retained alongside this attempt.

Local investigation found both `JS_Eval` calls violating the pinned header's
`input[input_len] == '\0'` contract. A non-NUL tail on the exact same bundle
reproduces a syntax failure with the same 10,772,221-byte JS peak as the phone.
`NativeInput.inc` corrects that concrete defect; matching memory alone is not
proof that all physical-device failure causes are resolved. Candidate 6 keeps
the same controller, media protocol, heap and time limits.

The corrected desktop binary passed a new complete AAC/native decode/30-second
seek run, with unchanged media and PCM hashes and 81,248,256-byte native peak
RSS. [Regression receipt](evidence/20261110T231137.127804Z-resolve_first-TV_SAMSUNG-aac.json).
Candidate 6's build and signing receipts are retained separately; its physical
background-next result remains pending. Broader parser versions, production
latency and route behavior retain their own P0 gates.

The [offline initialization comparison](ios-init-debug/README.md) retains 70 old
host cases, including 13 expected failures, and 56 corrected-host checks. All 66
calls reaching the corrected evaluator satisfied the NUL contract; no HTTP was
started. The user deferred the next phone run and requested macOS P0 work first.
Candidate 6 is signed and retained, but was not installed or run on the phone.

## Resources, evidence and reproduction

`stage-budget.json` SHA-256 is
`11328d623982202fe8b57fd54532cd2c378cd222a6688c8578be8bcdf6478a44`.
The original 8 GiB scratch / 40 GiB free-space guard and 1 GiB source allocation
remain; parser/transport/integration subbudgets are 400/200/300 MiB. The former
512 MiB runtime diagnostic exception does not apply. A decoder diagnostic has
three independent handles, each with at most 16 MiB network delivery, so its
total budget is 48 MiB; it retains one media file and incremental PCM hashes.
See `decode-stage-limits.json`, SHA
`bd4e8c81fc5c670b9ea29ff655eb65d8d94d2f38a6b1abda3f73735fff6b03f6`.

All build/probe commands run through the frozen parent `run_guarded.py` with
allocation `source`. `build_integration.py` captures inputs before compilation
and verifies them afterward; `run_integration.py` refuses stale source/binary/
bundle combinations and writes redacted immutable receipts. `build_ios.py`
requires that host snapshot and verifies iOS-specific inputs before and after
compilation. Signing and physical-device interaction are separate coordinator
steps. Previous failures, successful-but-superseded builds and cleanup journals
remain visible; compiler caches are not retained as evidence archives.

All new application logic is independent MIT code. Dependency notices and
versions are retained in the parser/runtime/transport reports and the original
audio evidence; no BitChord implementation or tests were copied. LGPL static
linking remains a prototype configuration, not a completed release/relinking
decision.
