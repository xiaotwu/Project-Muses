# P0 native source adapter proof

Status: **source playback gate remains open**. Catalog/native-runtime feasibility is established. Neither metadata nor a first-byte success demonstrates a stable playable source.

## What is pinned

- YouTube.js `18.3.0` (MIT), npm lock including transitive integrity hashes.
- QuickJS `2026-06-04` (MIT), archive SHA-256 `b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a`.
- esbuild `0.28.0` (MIT, build only); web-streams-polyfill `4.2.0` (MIT).
- The unused early candidate fast-text-encoding `1.0.6` remains in the lock (Apache-2.0) but is not imported into the runtime bundle. Encoding uses Foundation.
- Transitive protobuf includes Apache-2.0/BSD-3-Clause, fflate MIT, meriyah ISC. Retain their notices if distributing a derived app. No GPL BitChord source or tests were copied.

`NativeHost.m` embeds QuickJS directly in the native executable. `URLSession` performs HTTP; Node/esbuild are build tools only. No browser, Node/Deno runtime subprocess, cookies from an existing session, account credentials, Keychain, or WebView are used.

## Findings (2026-11-10)

| Gate | Observed result |
|---|---|
| QuickJS native catalog | Pass: 20 public video results, 20 continuation results, music search returned 29 sections. Search 422 ms, continuation 454 ms, music search 460 ms in the recorded run. |
| Public direct-URL metadata/first byte | Pass on the documented IOS client for the Blender Big Buck Bunny sample: 26 formats / 4 audio, AAC itag 140, HTTP 206, 65,536 bytes in 153 ms. Runtime peak allocation 10,576,337 bytes. |
| Consecutive media data | **Fail**: both Big Buck Bunny and Sintel fetch the first 1 MiB, then the next 1 MiB receives HTTP 403. Also fails after matching upstream `FormatUtils.download` range query + cpn + STREAM_HEADERS. Full sample files were not produced. |
| QuickJS full player extraction | **Fail**: current 2.66 MB player source exhausts both the approved 64 MiB heap and an explicitly separate 128 MiB experiment. Custom allocator measured the ceiling; no claim of success at larger budgets. |
| JavaScriptCore alternative | Actual full player retrieval/extraction succeeds in 1.832–1.878 s, at roughly 226–229 MB process peak RSS. It still does not fix IOS continued-media 403. WEB returns 40 formats but zero direct URLs/ciphers and a SABR endpoint; the current direct-format path fails with `No valid URL to decipher`. |
| IOS HLS fallback | Manifest is not supplied for the public sample in the observed response. |
| Cancellation | Native request cancelled; JS receives AbortError in 1 ms. |
| Heap exhaustion protection | Allocation test stops with out-of-memory before the 64 MiB ceiling. |
| Untrusted player code isolation | Separate QuickJS context has no fetch/native request/process; an infinite script is interrupted after 1,000 ms. |
| Whole-runtime deadline | Infinite script exits around the configured 2 s probe deadline; the ordinary operation budget is 90 s. |
| Physical iPhone | Coordinator owns deployment and receipts. The first lifecycle candidate failed at UIKit's iOS 27 scene requirement; the final candidate uses UIScene. Calibration execution is tracked separately from source playback, and has no bearing on the failed complete-source gate. |

All pass/fail receipts are retained under `evidence/`. They contain counts, formats, time, resource metrics, and status categories. They do not contain signed media URLs, request headers, authentication data, or raw provider responses. Early development failures (circular import and unknown response-length signedness) were corrected before the retained successful catalog/first-byte evidence. Earlier failed gate receipts remain; they are not overwritten.

## Architecture consequence

Keep the source gate open before production cutover. A small embedded runtime is viable for catalog and supported direct-URL source operations. YouTube.js's current full-player AST extraction is not viable inside the approved 64 MiB worker. Increasing that worker to 128 MiB did not solve it. JavaScriptCore proves that extraction can run natively, but its public API lacks a hard per-context heap limit; the CLI experiment's external 256 MiB RSS/95 s supervisor is **not** an iOS budget implementation.

The subsequent 403 remains a provider/client/transport capability failure in this tested adapter, not an established global outage or a proved attestation diagnosis. Authenticated paths and challenge workarounds were not attempted. Current source support needs a maintained permitted transport path, explicit capability errors and consecutive-data proof. Catalog success and Android reference-app progress must not be used as substitutes for that gate.

## Maintained native alternative assessment

The primary repository [alexeichhorn/YouTubeKit](https://github.com/alexeichhorn/YouTubeKit) was checked at commit [`7f75a2299dc329c0b7855afb25d47663a02855cb`](https://github.com/alexeichhorn/YouTubeKit/commit/7f75a2299dc329c0b7855afb25d47663a02855cb), dated 2026-10-31. Its code is MIT, with a bundled yt-dlp/ejs helper explicitly marked Unlicense, Meriyah and astring resources. The package has no external Swift dependencies and uses native Swift/URLSession plus JavaScriptCore on iOS/macOS. It has an optional remote fallback; the proof explicitly selected only `.local`, with OAuth off, no credential cache and a native ephemeral no-cookie allowlist. The optional remote service was never contacted.

This is materially different from the tested YouTube.js IOS path: current local default clients are `tvSamsung`, `visionOS` and `web`; its newest change exposes `availableAt` / `waitUntilAvailable()` from preroll timing. The upstream explains that a premature request can receive 403. That provides a concrete capability to model and verify, **not proof that preroll timing caused our observed failures**. Its extractor still embeds a full Meriyah/JSC AST route.

One bounded local-only continuity attempt was made with native networking, a 75 s external deadline and a 256 MiB observed process-RSS ceiling. It was terminated at 270,155,776 bytes observed RSS before it returned streams, so media continuity was **not established**. The external guard samples every 50 ms and is not a hard allocation limit. The failed receipt and upstream/log-suppression patch provenance are retained. Raw upstream log calls are replaced with no-op logging only in the scratch checkout to avoid leaking dynamic stream data; extraction/network logic is otherwise unchanged. A later wrapper-only stdout-flush fix is retained for repeatability and was not used to convert this failed run into a pass.

The coordinator then explicitly authorized one **diagnostic budget exception**, 512 MiB observed process RSS / 60 s / at most 16 MiB media, to separate resource cost from source capability. Production limits were not changed. This reached extraction: 34 streams including 6 AAC, 5 native requests, about 5.1–5.4 s. The first selection exceeded the declared media-length bound; after selecting the highest AAC explicitly within 16 MiB, the chosen length was 15,479,228 bytes and `availableAt` required no wait. The process then exceeded the diagnostic ceiling at 541,786,112 observed RSS bytes before a first media chunk completed. No continuous media or full-file result was established, and no larger runtime budget was attempted. Each attempt has a separate retained receipt. One redundant run used the last successful binary after an intermediate wrapper compile failure; it repeated the length-bound stop and is not treated as new evidence. The runner now verifies a successful-build source/binary hash receipt before execution.

Next source work should first add a typed availability time / retry-at capability and distinguish direct formats, HLS and SABR transport. Then implement or select a bounded native parser/solver and prove consecutive data plus decoding using fresh unauthenticated samples. YouTubeKit is a maintained candidate/reference, not an approved replacement or a passing low-memory solution. Keep its optional remote fallback outside the approved local-runtime architecture unless separately authorized.

Concrete follow-up gates:

1. Prototype player preprocessing with a native parser and explicit allocation accounting, then execute only the extracted solver in the existing 8 MiB / 1 s QuickJS isolation. Record cold extraction as well as versioned-cache reuse; a warm cache cannot excuse an unbounded cold path.
2. Model direct/HLS/SABR transport, URL lifetime and provider-advertised availability time as explicit source capabilities. A SABR-only response must select a SABR adapter or return a typed unsupported-transport state; it must not be sent to a direct-URL downloader.
3. Connect native media reads to a bounded native AVIO/ring-buffer bridge, with cancellation, backpressure, aggregate buffering limits and URL refresh. Keep media bytes out of the JS response-buffer path.
4. Require successful nonoverlapping range progression, a complete bounded sample and decoding/seeking before accepting an adapter. Then validate fresh-next resolution during an instrumented locked-device run when the user is available; calibration audio alone does not satisfy that gate.

## Native host contract and limitations

- QuickJS main heap: 64 MiB. Stack: 1 MiB. Actual allocation peak tracked by a counted allocator.
- Isolated player evaluator: 8 MiB heap, 512 KiB stack, 1 s deadline, no native networking/host capabilities.
- URLSession: ephemeral, no cookie storage or URL cache; HTTPS allowlist for youtube.com and googlevideo.com subdomains; redirects rechecked.
- Four active HTTP requests; 1 MiB request body; 16 MiB response limit checked on headers and every received chunk; 20 s request/25 s resource timeout.
- The P0 response bridge buffers a bounded response before exposing a ReadableStream. It is **not** a production streaming/backpressure implementation.
- URL, Fetch, UTF-8, timers, abort and Headers shims implement the tested paths, not complete WHATWG conformance. File/FormData intentionally fail if called. No authentication/cookie persistence or user library state.
- Cache is disabled. Complete proof media would occupy at most two 16 MiB task-owned files; failed partial files are never handed to the audio decoder. The prototype is not an offline-download manager.
- App trace is capped at 512 JSON lines. A run does not edit user music data or installed production apps.

## Reproduction

All builds/downloads/probes must run through the frozen parent guard, with `--allocation source`. Scratch allocation is 1 GiB, aggregate task is 8 GiB, free-space floor 40 GiB. All npm, module and temporary caches are directed to scratch by the scripts.

```sh
python3 ../run_guarded.py --allocation source -- sh bootstrap.sh
python3 ../run_guarded.py --allocation source -- sh build.sh
python3 ../run_guarded.py --allocation source -- python3 run_probe.py catalog
python3 ../run_guarded.py --allocation source -- python3 run_probe.py media_direct
python3 ../run_guarded.py --allocation source -- python3 run_probe.py background_first
python3 ../run_guarded.py --allocation source -- python3 run_probe.py background_next
python3 ../run_guarded.py --allocation source -- python3 run_probe.py media
python3 ../run_guarded.py --allocation source -- env P0_HEAP_MIB=128 python3 run_probe.py media
python3 ../run_guarded.py --allocation source -- sh build_jsc.sh
python3 ../run_guarded.py --allocation source -- python3 run_jsc.py player_first
python3 ../run_guarded.py --allocation source -- python3 run_probe.py hls_probe
python3 ../run_guarded.py --allocation source -- python3 run_probe.py cancel
python3 ../run_guarded.py --allocation source -- python3 run_probe.py memory
python3 ../run_guarded.py --allocation source -- python3 run_probe.py sandbox
python3 ../run_guarded.py --allocation source -- python3 run_probe.py interrupt
```

`run_probe.py` accepts only fixed probe names; `run_jsc.py` enforces the experimental process RSS limit. Failed gates intentionally return nonzero. `build_ios_objects.sh` links the same QuickJS/URLSession code with the audio agent's frozen iOS objects, then stages an **unsigned** app; signing/deployment belongs to the root coordinator. `collect_evidence.py` copies bounded sanitized receipts/locks and records hashes, allocated blocks, logical bytes and exact artifact ownership.

## Physical device harness

Bundle: `org.muses.p0.sourceprobe`. Prepared app: `/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/iphoneos/MusesP0Source.app`.

The app has catalog/start/stop controls. `--run-catalog` begins after 2 s; `--run-background` begins after 5 s. It activates a native playback AVAudioSession with mixWithOthers, starts the FFmpeg/miniaudio proof only after a complete bounded first source download, waits 30 s, resolves and downloads the next source **then**, creates the next decoder, and schedules a one-second transition. The sink watchdog stops at 90 s. Actual post-gain nonzero output and per-source consumed frames are recorded, along with app state and protected-data notifications. The source failure currently prevents this gate from reaching audio start, by design.

`--calibration` is a deliberately separate physical-device mode. It starts after 5 s using two root-generated 95 s AAC fixtures bundled as `calibration-first.m4a` and `calibration-next.m4a`. At 30 s it performs a **fresh live public catalog request**, then prepares the second synthetic decoder and transitions. Every row is labeled `calibration_synthetic_audio_live_catalog`; the header explicitly says `source_playback_gate: not_tested`. This can establish background embedded-JS/native-network and native-audio continuity, never complete online media playback. Accepted post-fade evidence requires two background snapshots after `transition_end_frame` with the first source's consumed count unchanged, the second source's consumed count increasing, post-gain nonzero output increasing and exactly one transition. Thirty-/ninety-second callbacks, remote Next and snapshots are scoped to the captured run generation so a stopped run cannot act on a replacement run.

Scene-enabled candidate 3 unsigned SHA-256: binary `bf92cf2e1d49c97b77e830cc4f034ebbec70d10d76f2c084e69907d9f5a88b3a`; JS bundle `c8734f93b2d3f7b4acb5689a9798ff76abcaed482b073e5cac46fe6133d5dd69`; Info.plist `b2431a68370bd0b514d58835720e6b18df7796ecb7433f64a2fdf1db0e94efd3`. Root's signatures necessarily change the signed binary hash and are recorded in its device receipts. Private crash reports and provisioning profiles are not part of this source evidence.

Coordinator run 4 demonstrates on-device public catalog (20 + 20 video results, 28 music sections), 10,607,318-byte peak JS allocation, 71,106,560-byte process peak RSS, native next-source consumption and nonzero output, one transition, zero underruns and the 90 s stop. An earlier device run failed networking with `NSURLErrorNotConnectedToInternet` (-1009); it remains a failed network observation. The user's audible confirmation is recorded by the coordinator. **Lifecycle context remains unverified:** candidate 3 logged a cached label only on active/background callbacks and omitted inactive, so the reported lock state cannot be judged from that label. Do not call the user’s lock action unsuccessful or relabel these runs as a proved background failure.

Candidate 4, not installed by this agent, corrects instrumentation. It logs `sceneWillResignActive` and `sceneWillEnterForeground`, and samples actual `UIApplication.applicationState`, `UIWindowScene.activationState` and protected-data availability together on the main thread into one immutable atomic snapshot for every row. Numeric states, sample time, main-thread flag and last callback label are separate. UI text updates are suppressed outside foreground-active. Apple distinguishes inactive from both active and background; the old two-state cache was insufficient. New unsigned binary SHA-256: `cb62c7d1a67b9aeadbe9b3264dd659a400b5704149ce52f46524e72d7d29922a`; source `iOSMain.m` SHA-256 `9d43d9b844a47dc5e73a9ea5396e7b5877f20c4177b6b7a52ba0fa5c5fc040cd`. JS/plist/fixtures are unchanged. No additional physical test was requested by this agent.

Trace: app Documents `p0-source-trace.jsonl`. Media: app Library/Caches `MusesP0Source/{first,next}.m4a`. No Keychain, app group or production preference domain. iPhone lockscreen evidence requires root-coordinated physical observation; source preparation/build is not that evidence.

## Primary references

- [YouTube.js source and MIT license](https://github.com/LuanRT/YouTube.js), [platform contract](https://github.com/LuanRT/YouTube.js/blob/main/src/platform/README.md), [download implementation](https://github.com/LuanRT/YouTube.js/blob/main/src/utils/FormatUtils.ts).
- [QuickJS official release, embedding and MIT license](https://bellard.org/quickjs/), [C API resource limits](https://bellard.org/quickjs/quickjs.html).
- [JavaScriptCore JSContext](https://developer.apple.com/documentation/javascriptcore/jscontext), [URLSessionConfiguration.ephemeral](https://developer.apple.com/documentation/foundation/urlsessionconfiguration/ephemeral).
- [Apple sceneWillResignActive](https://developer.apple.com/documentation/uikit/uiscenedelegate/scenewillresignactive(_:).md), [UIApplication inactive state](https://developer.apple.com/documentation/uikit/uiapplication/state/inactive.md). The installed iOS 27.2 SDK headers additionally define separate foreground-active, foreground-inactive, background and unattached scene states.
- Public Blender samples: [Big Buck Bunny](https://www.youtube.com/watch?v=aqz-KE-bpKQ), [Sintel](https://www.youtube.com/watch?v=eRsGyueVLvQ).

## Retention and cleanup handoff

No irreversible cleanup or device installation was performed by this agent. Exact final allocated blocks, logical bytes, remaining APFS space and paths are in `manifest.json`. `media/first.m4a`, `media/next.m4a` and `media/jsc.m4a` are **failed partial downloads**, not complete media or user data. Retain bounded source/evidence; root should recoverably trash obsolete `deps/`, `downloads/`, `npm-cache/`, `YouTubeKit-7f75a2299dc329c0b7855afb25d47663a02855cb/`, `youtubekit-{build,cache,config,module-cache,probe,security}/`, `media/`, old CLI binaries, superseded signed candidates 1/2 and temporary compiler caches after recording the final stage receipt. The latest unsigned app, tested signed candidate 3, frozen iOS objects, synthetic fixtures, exact JS bundle and small pinned QuickJS source remain for the unfinished coordinator-owned device proof. No shared dependencies or operating-system managed paths are in this allocation. This agent recovered 0 bytes; cleanup is a root-coordinated recoverable operation, not a silent disposal.

`cleanup-inventory.json` supersedes broad directory descriptions with exact recoverable-trash candidates and protected retention, including the coordinator's explicit small relink/source set. No compiler cache is needed as an evidence archive. Root owns private signing material and executes the cleanup after verifying this inventory and its own frozen plan. Source evidence retains small manifests/receipts and pinned reproduction scripts.
