# P0 source-v2 iOS controller

This is an isolated test controller, not shipped product UI. It has not been installed or exercised on a phone by this agent. The coordinator owns the native source wrapper, final iOS link, plist, signing, deployment and user confirmation.

## Integration contract

Compile `iOSMain.m` with ARC and the iPhoneOS SDK. Its local `RunPolicy.h` is included directly. App/scene classes are `P0V2AppDelegate` and `P0V2SceneDelegate`; the plist must name the latter and retain `UIBackgroundModes = audio`. Link the existing `audio/p0_audio.h` ABI, frozen FFmpeg/miniaudio iOS objects, UIKit, AVFAudio, MediaPlayer and the coordinator's source-v2 host.

The host provides:

```objc
int P0V2RunSource(NSString *bundle, BOOL next);
void P0V2Cancel(void);
void P0SetMediaDirectory(NSString *directory);
void P0SetMediaHandler(void (^handler)(NSString *completePath, BOOL next));
void P0SetLogHandler(void (^handler)(NSString *sanitizedJSON));
```

`P0V2RunSource` is serial, bounded to 45 seconds per operation, and releases the JS runtime before native media transfer. It calls the media handler only after a complete validated file, at most 16 MiB, exists in the provided directory. Media never enters JS. It must not run the desktop full/seek comparison passes before playback. Descriptor/availability/URL policy and cancellation belong to that host; HLS/SABR remain explicitly unsupported by the direct transport. The controller does not guess a substitute source or replay a calibration fixture on failure.

The current real-time audio ABI already uses FFmpeg to decode local AAC/M4A and Opus/WebM into two bounded PCM rings and one miniaudio shared output. It does not take an HTTPS URL or an `MTHandle`. No new decoder is necessary for this complete-file prototype. Native AVIO streaming into that real-time sink remains separate future work.

## Run and timing

Normal opening is idle. Manual Start or the explicit coordinator launch flag `--run-background-v2` starts a run; that flag waits five seconds. Any manual Start/Stop consumes the pending auto-start, preventing an old delayed block from restarting a stopped run.

1. Inventory the owned cache, reserve 34 MiB (32 MiB media plus 2 MiB trace), create a new run directory, and resolve/download the first source.
2. Only its complete-file callback activates a playback session with `mixWithOthers`, then starts the existing audio ABI with `audible=1`, 0.12 app gain and a 90-second native watchdog. No system volume or route is changed. The timestamp is device-start completion, **not first audible sound**.
3. At audio start +30 seconds or later, read actual `UIApplication.applicationState` and the attached `UIWindowScene.activationState` together on the main thread. Both must be background. Otherwise record `not_background`, cancel and stop. Recheck immediately before the source call. Remote Next is disabled.
4. Only then call `P0V2RunSource(bundle, YES)` in a fresh source operation. Its completed file creates the next decoder. The existing ABI schedules a one-second lead and one-second crossfade after preparation. Fixed source IDs may be selected beforehand; no second descriptor, signed URL, media file or decoder is prepared in advance by the controller.
5. The native device watchdog stops audio at 90 seconds from native start. The independent 100 ms observer requests whole-run cancellation at the corresponding controller deadline. Sources are limited separately to 45 seconds each; first-source preparation precedes audio and is not part of that 90-second interval.

`background` is an OS state, not proof that the physical screen is locked. Protected-data availability, scene callbacks, numeric native states, main-thread flag and sample time are recorded separately. Human lock action and audibility still require coordinator-observed device evidence.

## Ownership and cancellation

- `sourceQueue` serializes both source operations and owns the host's process-global JS state. A pending-operation counter includes queued work. The media/log handler captures that operation's run object.
- `audioQueue` alone starts, prepares, snapshots and destroys the native audio object. The same controller lock orders media enqueue and cancellation, so a stale callback cannot queue behind Stop and resurrect audio.
- Stop first atomically latches the reason and calls `P0V2Cancel` immediately. It then enqueues audio teardown. The 100 ms monitor reasserts source cancellation until the source call returns, covering an entry/reset race in the host. It never frees JS or destroys an `MTHandle` itself.
- Native `prepare_next` and initial prepare can occupy the audio queue for up to their existing five-second preparation bound. Manual Stop is therefore not claimed instantaneous. The native 90-second watchdog remains independent of that queue. Snapshots never overlap destruction.
- A run remains current until every queued source call returns and audio teardown finishes. Only then can Start create a new generation. Old observer/timer/remote blocks check their immutable run identity. Main never synchronously waits for the source/audio/evidence queues; lifecycle reads from those queues synchronize onto main.

## Resource and evidence limits

The independent observer samples whole-process current RSS every 100 ms, including source work and ongoing playback, and cancels above 256 MiB. Final `ru_maxrss` is also recorded. This is an observed process bound with cancellation, **not a hard allocator ceiling**; short overshoots between samples and native allocator high-water retention remain possible. The host's QuickJS/parser/transport limits are separate.

Owned paths are `Library/Caches/MusesP0SourceV2/run-UUID/media/` and sibling `trace.jsonl`. Completed and partial source files together are limited to 32 MiB per run; the entire v2 cache has a 64 MiB logical-byte cap. Admission reserves the maximum new run size before work; active observation re-inventories the directory, rejecting links, unexpected node types, read errors and inventories above 4096 entries. Allocated bytes are reported separately. No prior run is silently removed when full. The coordinator must inventory/export and recoverably clean owned files before another run if admission refuses it.

All created directories and the trace explicitly use `NSFileProtectionCompleteUntilFirstUserAuthentication`. The coordinator's native transfer creates partial media with that protection class at creation; it must not depend on unverified inheritance. Actual file protection while locked is pending device validation.

Trace is append-only and limited to 512 rows / 2 MiB, with eight terminal rows reserved and a 4096-byte row maximum. Numeric values and a small string-field allowlist survive; URL, Visitor, profile, token, cookie, header, path and filename fields are dropped at this boundary. No raw exception text is retained. UI text updates only in foreground-active. A trace-limit or write failure stops the run rather than pretending an unrecorded run passed.

## Completed offline checks

All commands ran under the frozen parent `run_guarded.py --allocation source`. `verify.py` performs an iPhoneOS 27.2 SDK syntax check with `-Werror`, then exercises the actual shared policy with normal and ThreadSanitizer builds: no early next, both-state background requirement, single next claim under 100 rounds × 16 threads, cancellation reason latching, independent replacement state, and total-file/trace arithmetic boundaries. These are not UIKit runtime or phone cancellation tests.

`run_real_abi.py` compiled the **unchanged** original `audio/probe.cpp` with `P0_LIBRARY_ONLY`, restored only the hash-verified miniaudio header and macOS backend object into active scratch, and reused the previously verified four LGPL-only FFmpeg archives read-only. It read the coordinator's completed public files without copying or modifying them:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| AAC, 6 channels, 48 kHz, itag 256 | 15,479,228 | `f9bf28dcef3bd5b8cad072301303d5e22fdb15252c08520786fb730932828f03` |
| Opus, 2 channels, 48 kHz, itag 251 | 10,258,925 | `08dd9fc36d077d0dd39b51f039dc35135e678aa16bb405175d85d34af12605f6` |

Both are representations of the same public video; this checks codec/input transition, not distinct-recording identity. The six-second **muted** shared-output test passed: one transition, 288,512 clock frames, first/next consumed 86,848 / 249,664 frames, zero underruns, zero post-mute nonzero frames, native watchdog stop and unchanged clock after stop. Sampled peak RSS was 23,642,112 bytes. It did not measure human audibility or first-real-sound latency, and it did not change system output routes or volume.

Reproduce from this worktree:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source -- python3 engineering/p0-2026-11-10/source-v2/ios/verify.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source -- python3 engineering/p0-2026-11-10/source-v2/ios/run_real_abi.py
```

The second script requires the exact retained public files and archived dependency hashes, and always uses `audible=0`. It does not fetch replacements. `evidence/manifest.json` freezes the bounded receipts and source hashes. Old compiler helpers are inventoried there for coordinator cleanup; no irreversible disposal is performed here.

## Still unproved

No new iOS binary was installed or phone operated by this agent. Actual source-v2 background fresh-next resolution/transfer, locked file access, continuous audible output, 90-second whole-chain termination, observed iOS RSS and human hearing confirmation remain device gates. Desktop decode equality and the muted ABI check cannot substitute for them. Neither this prototype nor the earlier calibration proves a frozen 30-source corpus, 100-attempt baseline, four-hour endurance, first-sound performance or production parity.
