# macOS streaming P0, second bounded prototype

**Result:** the final candidate passed 17 controlled local cases and one public Opus prefix/seek-to-tail run, with all native output muted. It now separates input failure, cancellation, decoder/SWR completion and fully consumed output; freshly rebuilt runtime/parser objects and every linked archive member target macOS 26.0. Execution was on macOS 27.2 only. This is an isolated CLI prototype, not a production application change, audible acceptance or a general player state machine.

Final source: `Streaming.cpp` SHA-256 `b1adba3d2375676d270a144dcd8b3e92463173ea0d671c951e7e7a58b2b19b28`.
Authoritative scratch under `/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-streaming/v2`:

- Build: `build-20261111-004247`; build receipt SHA `37ade4700255e74564f36e68404bcb54733238003c81584b427d237b1d95c2c9`.
- Local: `local-20261111-004309`; guard receipt `7fa02e6627c14fd79a4fe50e05dbeb5d`.
- Public: `public-20261111-004412`; guard receipt `84fd7f152b6542d898857330ab3604e9`.

Directory timestamps are UTC. The first-stage `streaming/`, original `audio/`, and source integration evidence remain unchanged. The final independent read-only review is `REVIEW-V2.md`, SHA `3964193ae8a54060924bab050454afbe5e9d1fd484fa9a41d4b0d9384c9ad8eb`.

## What the lifecycle proof now establishes

Normal completion requires demux EOF without a transport/AVIO error, codec drain to codec EOF, repeated SWR flush until it returns zero, then consumption of the sealed PCM ring. Before publishing `Ended`, the producer publishes its final write index. After observing `Ended` with acquire ordering, the callback retries a previously empty pop and only marks ring completion when its read index equals that seal. The controller stops the device and joins the worker before inspecting hashes. A failed pop that happened before the final publication cannot prematurely declare completion.

Seek first prevents old PCM consumption, waits until the producer has finished every old-generation write, then lets the callback discard/acknowledge the old ring. The worker seeks only after that acknowledgment. Seek acceptance and entry into EOF drain are serialized outside the callback; a sealed input explicitly rejects a new seek. A valid tail shorter than the 8,192-frame preparation threshold still completes. Each seek creates a fresh codec and SWR context, uses integer origin ticks and requests 120 ms of preroll. The actual demuxer seek point is separately recorded and can be substantially earlier: the 40-second local Opus fixture selects PTS 34.994 for target 39.95. **120 ms is not a bound on actual work.** No test seeks by intentionally downloading or decoding the whole recording from zero.

A non-cancellation transport error is latched when AVIO observes it. A later Stop cannot turn it into a successful cancellation or bounded-probe completion. Final checks inspect both inputs and require the branch's permitted termination reason; resource/deadline stops cannot count as a behavioral pass. The controlled failure-return barrier confirms an already observed network error remains `input_failed` even when the controller requests a normal bounded stop before the decoder catch runs.

Cancellation checks run inside the callback; device stop/uninit precede worker joins and handle destruction. Full-ring cancellation, active output cancellation, and a failure after first output are covered. Forced cancellation specifically inside codec drain/SWR drain, an injected RSS/deadline trip, and a deterministic final-publication hook were not separately run. The latter publication fix was independently reviewed and full-PCM drain regressions passed; this is not an exhaustive concurrency proof or a new ThreadSanitizer run.

## Local results and reference boundaries

All 17 final cases exited successfully with the expected terminal classification. Expected-error cases are labelled `expected_failure_observed`, not successful playback. Peak externally sampled RSS was 25,477,120 bytes.

| Case family | Evidence |
| --- | --- |
| AAC/M4A 44.1 → 48 kHz, complete | 64,497 frames; producer, callback and independent complete-file reference SHA equal |
| AAC/Matroska, unknown duration, complete | 64,644 frames; **17 additional SWR drain frames**; complete PCM and tail match |
| Tiny AAC | 3,985 frames, below prefill threshold; normal ring drain; seek after producer seal explicitly rejected |
| Opus, nonperiodic source with unique tail | Exactly 59,731 frames, not a multiple of 960; complete PCM SHA and tail match; decoder pre-skip/discard-padding retained |
| Positive-origin M4A | Full 65,613 frames and relative 1.30-second seek tail 3,211 frames match a zero-origin remux with identical encoded-packet hashes |
| Positive-origin auxiliary AAC/Matroska | Full 64,644 frames and relative seek tail 2,229 frames match the corresponding zero-origin reference under the bounded metadata rule below |
| AAC/Opus tail seek and held-publication seek | Producer/consumer/fresh-seek reference frames and SHA equal; seek acknowledgment waits for producer quiescence; stale queued PCM is discarded |
| First-block / second-range failure | Typed input failure; second-range failure is observed after output starts, while next preparation is deliberately pending |
| Error observed → Stop race | Failure latch survives later Stop and ends as `input_failed` |
| Full-ring / active output cancel | Full-ring cancel-to-join 54.890 ms in this attempt; after stop/join, consumption remains unchanged |
| Late AAC → Opus | One shared output, two owned handles/workers, one transition and correct post-transition input ownership |

`Reference.cpp` runs the unchanged frozen complete-file comparison decoder in a separate process, without a device. Full-input comparisons test complete decoded PCM. Seek comparisons test agreement with that decoder's **fresh seek path**, not with an exact slice of a decode that started at zero, and not with a universal timeline oracle. The 40-second Opus tail seek at 39.95 produces 2,424 frames versus the nominal 2,400-frame remainder: the previously observed 24-frame / 0.5 ms boundary remains disclosed. Equality of two FFmpeg paths does not erase it.

The short complete fixtures are smaller than one native window; their EOF tests do **not** prove partial-fetch startup. Early-output proof uses the longer fixtures and the public representation. All fixture audio is task-generated; no personal library or microphone input is used. Homebrew FFmpeg 9.0.2 is a development-only fixture encoder/remuxer, never linked to the prototype. The chosen runtime is the pinned LGPL-only FFmpeg 8.0 build. Fixture manifests preserve input/output hashes, commands, source sample counts and matching encoded-packet hash sequences.

## Positive origins and codec-delay limits

Positive AAC/M4A presentation start is converted to a relative timeline: seek adds the integer origin ticks, decoded PTS subtracts the origin, and a known duration is a length rather than an absolute end PTS. Bitrate-estimated duration is never used as a hard cutoff. The same-frame-count/different-PCM failure disappeared after integer tick selection and fresh codec/SWR contexts were introduced together; the experiment does not isolate one internal AAC mechanism as the cause.

The auxiliary AAC/Matroska fixture required a separate metadata check. The actual selected **FFmpeg 8.0** reports start ticks −23 for the zero-origin file and 977 for its shifted counterpart, timebase 1/1000, `initial_padding=1024`, unknown stream duration, and no packet skip side data. FFmpeg 9's metadata display alone was insufficient. The prototype only maps declared AAC padding when the container is Matroska, start is known, duration is unknown, trailing padding is zero, and declared padding is at most one second. It rescales that declaration into the container timebase and records the **0.0002199546-second quantization residual**. It does not hardcode a 1,115-frame crop or claim sample-exact padding removal.

An AAC padding declaration combined with a different container, unknown start, known duration, trailing padding, or a nonzero explicit packet skip/discard record is unsupported in this proof. These rejection branches were reviewed statically; a fixture was not run for every combination. Opus keeps its decoder's pre-skip/discard-padding handling and is not given a second manual AAC trim. Arbitrary edit lists, timestamp discontinuities and these unvalidated combinations remain open product work.

## One real public Opus run

The fresh native descriptor identified `aqz-KE-bpKQ`, itag 251, Opus 48 kHz stereo, 10,258,925 declared bytes. JavaScript was destroyed before native media handoff; media bytes stayed outside JavaScript. Public native output remained zero throughout. No newly downloaded public media file or signed URL was persisted.

| Event | Seconds from session action |
| --- | ---: |
| Native descriptor after JS disposal | 3.378693 |
| First validated block returned to AVIO | 3.555542 |
| First converted PCM | 3.556322 |
| First output callback consuming input PCM | 3.795313 |

Both PCM and callback events occurred after only 262,144 received bytes. The entire run used **333,050 bytes in two native range requests**, including the seek-to-tail operation. The seek target was 634.5 seconds; its actual first packet was PTS 634.374, with 5,736 converted preroll frames discarded. This is direct evidence of a local seek near the end, not a hidden full-recording replay. The 3,775 produced/consumed tail frames match the retained complete representation's independently decoded fresh-seek reference, SHA `e3e11c101250b2bbc6ea90ff14714c649f26fbaad967645378daa7baaa3e1cb9`.

The process took 4.415 seconds with peak externally sampled RSS 87,080,960 bytes. It ended `normal_eof` after seek, with sealed write/read both 55,999 and zero remaining ring frames. Cleanup recorded one output start/stop, one joined decoder worker and one destroyed handle. Pre-mute content was nonzero; submitted nonzero frames were zero. There were **2,816 underflow frames across the complete run**, equivalent to 58.7 ms. Counters were not split by phase, so they cannot all be assigned to a particular seek refill interval. This is not a seamless-seek claim.

“First validated block” is later than the network first byte. “First PCM” may include quiet samples. Callback consumption is neither hardware presentation nor speaker sound. The driver deliberately pauses before output to check backpressure; these timings are not optimized product-startup benchmarks. No human audibility, microphone/loopback capture, full-track continuous public playback, four-hour stability or 100-attempt reliability was measured.

## Consistent compilation target

QuickJS 2026-06-04, Tree-sitter 0.25.10, JavaScript grammar 0.25.0 and the native parser adapter were rebuilt from copied, hash-pinned source with `-target arm64-apple-macos26.0`. No new dependency download or global installation occurred. The previously rebuilt FFmpeg 8.0 archives and miniaudio 0.11.26 backend are reused only after checking their identities and deployment load commands.

`deployment.json` checks all 22 linked objects/archives/final binaries: 251 archive members plus 18 standalone objects/binaries, 269 load-command records total. `ar -t` member counts are matched to `otool -l` inspections. Every recorded minimum version is 26.0. Assembly objects with SDK `n/a` still require the correct platform and minimum version. The earlier target-version linker warnings are absent in the final build. Deployment evidence SHA: `6ca16a65b9e79203664dd1b13b03e63c5f91b6688499fe9fd17c4e31b48c845d`.

Host/toolchain remain macOS 27.2 (`26B123`), Xcode 27.2 (`27B52`), Apple clang 21.0.0 (`clang-2100.4.1.1`), SDK 27.2. Compiling for 26.0 is **not** execution evidence on macOS 26. No iPhone operation, app installation, production signing or notarization was performed.

## Failed attempts and reproduction

The following failures are retained, with exact recovered source snapshots whose SHA matches the original recorded candidate, inverse-edit scripts, to-final patches, compiler/test logs and original guard receipts. Historical sources were not merely approximated from the final implementation.

| Attempt | Failure / retained source |
| --- | --- |
| `build-002036` | FFmpeg 8 getter no longer declared; `history/Streaming-2539398d.cpp` |
| `build-002414` | Deployment inspector omitted SDK `n/a` assembly records; actual old script `history/build-b80073ae.py`, source `Streaming-3c3e4dcc.cpp` |
| `local-003128` | Positive M4A seek had equal 3,211-frame counts but different PCM; `Streaming-6211062a.cpp` and exact `run_local-f36912b1.py` |
| `local-003726` | Positive AAC/Matroska included extra leading decoded PCM; `Streaming-19355d1d.cpp` and unchanged current runner |

The first 13-case success is also retained; it was superseded after independent review found EOF-publication and cancellation-classification races. The final 17-case success does not rewrite those older findings. `history/manifest.json` records the exact source hashes; `REVIEW-V2.md` records the independent audit's version boundaries.

All generation, builds and execution used the original guard with allocation `audio`. The frozen subbudget gives `v2/` 96 MiB within the existing shared streaming **128 MiB** ceiling, not an additional 128 MiB. It retains the 40 GiB free-space floor, two-handle / 32 MiB aggregate received-body cap, 256 KiB windows, two 32,768-frame PCM rings, 90-second session deadline and 256 MiB observed process RSS ceiling. RSS observation is not a hard allocator limit. The existing miniaudio shared output and no-runtime-linking configuration are retained; no system volume, route or microphone setting was changed.

From `/Users/xiaotwu/Code/Project-Muses-P0`, using the already prepared pinned kit:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- python3 engineering/p0-2026-11-10/macos-p0/streaming-v2/build.py --plan-sha 63486f340224af3230b8add50e09bf66dd01dc0515ad31561dfb019d961f26ad --script-sha e431777ab5eda1103e0cbdd9f2220adf8e46e90463932dafa35efe241ee1bf12
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- python3 engineering/p0-2026-11-10/macos-p0/streaming-v2/run_local.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- python3 engineering/p0-2026-11-10/macos-p0/streaming-v2/run_public.py
```

A future public-source change must remain a recorded failure rather than being relabelled or retried until it passes. HLS/SABR, source-refresh retry, arbitrary queue replacement, device-change recovery, iOS/Windows runtime parity and actual product integration remain outside this stage.

## Retention and coordinator cleanup

`evidence/manifest.json` freezes current source/review hashes, successful and failed text evidence, exact inputs, deployment checks, history, toolchain and guard receipts. `evidence/cleanup-inventory.json` lists exact owned paths, per-file hashes, logical/allocated sizes and open-file observations. Keep `kit/`, the final `build-20261111-004247`, the two small fixture directories and `current-build.txt` for unfinished integration/reproduction. Older builds, duplicated run folders and the completed timeline diagnostic helper are eligible for the coordinator's recoverable Stage7 cleanup after verifying their copied evidence. This agent has moved/deleted no files and claims zero physical bytes recovered.
