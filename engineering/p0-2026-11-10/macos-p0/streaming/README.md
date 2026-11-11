# Native streaming P0 — macOS, muted

The independent prototype passed its bounded streaming proof: native range reads feed FFmpeg custom AVIO, bounded PCM rings and one shared CoreAudio output. Both generated AAC/Opus fixtures and two freshly resolved public AAC representations reached decoded PCM and output-callback consumption before the complete representation had been fetched. Every device output sample was zero. This is not speaker-first-sound evidence or integration into the production application.

The authoritative build is `build-20261110-234930`; its local run is `local-20261110-235204`, and its public run is `public-20261110-235239`, under `/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-streaming`. The earlier successful build and runs are retained as a separate instrumentation revision. The final revision conservatively samples the network counter with a read sequence: a racing observation forfeits the early-output assertion instead of understating bytes.

## Scope and ownership

`SourceAdapter.inc` is appended to a copied, hash-verified generated source host. Its `P0_IOS` define only excludes the old desktop main and complete-file diagnostics; this remains a macOS executable. It calls the existing metadata/parser proof, waits for its JavaScript context/runtime to be destroyed, checks the native descriptor and availability time, then creates an independent native `MTHandle`. Media response bodies never enter JavaScript. A second fresh metadata operation occurs only after first-input output is running. JavaScript for that second operation can coexist with the first native stream; it is destroyed before the second handle is handed over.

The copied host preserves expected video identity, source host policy, bounded public headers, expiry and availability checks. A known future availability time is waited for, with a 20-second cap and cancellation checks. The final next-source response advertised a five-second wait, which was respected. An unknown capability or unsupported transport is a failure, not a silent fallback. No signed URL, cookie, credential, visitor or profile identifier is written to the retained public trace. Public metadata identifiers and representation numbers remain for reproducibility. No public media file is created.

`Session` owns at most two handles and their decoder workers. It never lends these handles to the old source host's single-handle control. Cancellation marks the session, cancels both handles and the active metadata operation, then stops the shared output. Destruction joins the watchdog, uninitializes the device, joins decoder workers, and only then destroys handles. The callback takes no transport, decoder or lifecycle mutex. Seek uses a generation handshake: the callback discards old queued PCM, the worker seeks and flushes, then new PCM becomes eligible. Seek during a transition and repeated next replacement are deliberately outside this proof.

| Bound | Implemented value |
| --- | --- |
| Native transport | At most two handles; 16 MiB representation and received-body budget per handle; aggregate at most 32 MiB |
| Pull window | One 256 KiB block per handle; 512 requests maximum; 5-second request timeout |
| PCM | Two 32,768-frame stereo float rings, 524,288 bytes total; 8,192-frame conversion block per decoder |
| AVIO / probe | 4 KiB AVIO buffer, 64 KiB probe, 1-second analysis allowance, at most four streams |
| Decode | AAC or Opus; one codec thread; 8–192 kHz and 1–8 source channels; 48 kHz stereo output |
| Runtime | 90-second session deadline; 100 ms process RSS observation; 256 MiB observed RSS ceiling |
| Metadata | Existing 64 MiB JavaScript limit; 45-second cancellable native operation envelope |
| Scratch | 128 MiB local allocation; original audio/global guards and 40 GiB free-space floor |

The network budget counts native received response-body bytes, including refetches; it is not a TLS/wire-byte measurement. The RSS ceiling is sampled observation with cancellation, not a hard allocator limit or a proof that short spikes are impossible. No allocation-limit or 90-second watchdog fault was injected in this stage.

## Final local evidence

All eight controlled cases passed. The server accepts loopback only, emits exact Content-Range/Length/ETag values, and sends 16 KiB chunks with 20 ms spacing. The production transport binary does not enable test loopback.

| Case | Observed result |
| --- | --- |
| AAC 44.1 kHz stereo, 488,694 bytes | PCM and callback after 262,144 received bytes; no underrun |
| Opus 48 kHz stereo, 657,042 bytes | PCM and callback after 262,144 received bytes; no underrun |
| Late AAC → Opus | Next handle absent initially; one transition; first input stops being consumed after fade; next consumption continues; no underrun/clipping |
| AAC seek to 30 seconds | First eligible PCM PTS 30.00000609; 32,768 stale queued frames discarded; 8,192 underflow frames during refill |
| Opus seek to 30 seconds | First eligible PCM PTS 30.0; 32,768 stale queued frames discarded; 18,176 underflow frames during refill |
| Disconnect halfway through first block | 131,072 bytes received, zero validated/decoded bytes; numeric network error retained; no device start |
| Server ignores Range | Typed range-unsupported rejection; no device start |
| Cancel stalled I/O | Cancellation to joined decoder: 1.417 ms in this local attempt; no device start |

Peak externally sampled RSS across these cases was 25,804,800 bytes. Both PCM rings remained within capacity and the native window within 262,144 bytes. A deliberate 300 ms pre-output pause lets the first ring fill; unchanged network counters across that pause demonstrate backpressure. Consequently these timings are not optimized startup benchmarks. Dynamic seek intentionally permits a refill gap and does not establish seamless seek.

The two owned, generated fixtures are frozen by SHA-256:

- AAC: `4e6484d0639472123d8932f1d07f61f242de91a58c07ad5f70adb21fb3ea360d`
- Opus: `eaa92a8f8f2f21cd40072556ae641136b4ed45bec892bba22f927b50a9f5abf6`

The observed seek PTS values apply to these fixtures and this FFmpeg conversion path. They do not establish a universal Opus sample-alignment bound or explain the older proof's 24-frame difference. Natural end-of-stream/SWR drain and complete-track duration accounting were not exercised here.

## Final public-source evidence

One 16.032-second process resolved two public identities using the frozen TV_SAMSUNG metadata adapter, performed native range reads and rendered real decoded content into the muted callback. The first source was `aqz-KE-bpKQ`, AAC itag 256, 48 kHz / six channels, 15,479,228 declared bytes. The second was `eRsGyueVLvQ`, AAC itag 140, 44.1 kHz / two channels, 14,373,564 declared bytes. This stage does not claim a complete-file hash of either representation: only bounded streaming prefixes were read.

| Event, seconds from session action | First source | Fresh next source |
| --- | ---: | ---: |
| Native descriptor after JS disposal | 3.545569 | 9.507574 |
| First validated block returned to AVIO | 3.681298 | 14.575815 |
| First decoded PCM | 3.683304 | 14.576467 |
| First callback consuming this input's PCM | 4.060060 | 14.822695 |
| Received bytes at first PCM / callback upper bound | 262,144 / 262,144 | 262,144 / 262,144 |

`first_validated_bytes_ns` timestamps the completed, validated pull block returned to AVIO. It is not the HTTP/TCP first byte. `first_decoded_pcm_ns` marks a converted PCM block, which may start with silence. Callback timestamps mark callback entry/consumption, not hardware presentation; the buffer submitted in this experiment contains zeros. No microphone, loopback capture, human listening confirmation or speaker-first-sound timestamp was used.

The run used 786,432 response-body bytes total, three native range requests, 2,236 output callbacks and 572,416 clock frames. It completed one transition with zero underflow frames and zero clipped samples. Pre-mute mixing contained 572,308 nonzero frames; submitted nonzero frames were zero. External sampled peak RSS was 97,370,112 bytes. Cleanup recorded one output start/stop, two joined decoder workers and two destroyed handles. No complete media download was necessary before output-callback consumption.

This is a short streaming capability proof. Public Opus streaming, arbitrary source identities, URL refresh/retry, HLS/SABR, EOF drain, output-device change recovery, pause/resume, an application queue/state machine, 100-attempt reliability and four-hour runs remain unvalidated here. It does not measure the macOS 0.6.3 baseline, provide the frozen 30-item identity corpus, or establish iOS/Windows parity. The old full-file AAC/Opus and native-AVIO proofs remain separate evidence.

## Inputs and reproduction

The build copies exact inputs to active scratch and verifies hashes before compilation. It reuses the newly rebuilt stock LGPL-only FFmpeg 8.0 static archives and the miniaudio 0.11.26 backend object from the preceding relink kit. `MA_NO_RUNTIME_LINKING` and a single shared CoreAudio device remain in use. No Homebrew codec library is linked. LGPL relink feasibility and notices are documented by the separate, unchanged relink evidence; this stage makes no new product-distribution compliance claim.

| Frozen input/output | SHA-256 |
| --- | --- |
| Root validated generated host | `f37159192477d9ddc8316d96f7884185d59b27e301e1152124bb684e99dd5fa8` |
| Root validated JS bundle | `a258ea65c14b005052f88f6c12c85fef1a56764ba6fd93aee0ce8936ecb0115f` |
| Root source binary used to bind provenance | `809e5aec293e57863d98b081f289d08e9819f3df2d2a5bbad387305c9e997000` |
| Final local streaming binary | `171f7957e8f07044fc516e10bd91791ae2bf06998f5ace04bc5ad174f7af659e` |
| Final public streaming binary | `7e8d805d9e96fa153829352fafe488ead25475a1a45cae365a87bcc25c26437f` |
| Final build receipt | `1c7b1979e74ec309aaccd7ca9dc9b467212d641c4d003e5043aa116c093e7f8f` |

Toolchain: Xcode 27.2 (`27B52`), Apple clang 21.0.0 (`clang-2100.4.1.1`), macOS SDK 27.2; host macOS 27.2 (`26B123`) arm64. The link command targets macOS 26.0, but reused QuickJS/parser objects were built for 27.2. Those linker warnings are retained. Only the current 27.2 host was validated; a consistently targeted dependency rebuild is required before claiming macOS 26 support. No app installation, signing/notarization or production UI change was part of this stage.

Run from `/Users/xiaotwu/Code/Project-Muses-P0` with the frozen parent guard:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- python3 engineering/p0-2026-11-10/macos-p0/streaming/build.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- python3 engineering/p0-2026-11-10/macos-p0/streaming/run_local.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- python3 engineering/p0-2026-11-10/macos-p0/streaming/run_public.py
```

Live source availability can change. A failed attempt must remain recorded; repeated failures must not be relabelled as a pass. The public runner retains only sanitized JSON events and raw-output hashes, with bounded in-memory output collection. No raw signed descriptor is an evidence artifact.

## Stage closure

`evidence/manifest.json` binds both successful revisions, exact build inputs/commands, local traces and server requests, sanitized public traces, guard receipts, source hashes and this report. `evidence/cleanup-inventory.json` lists exact owned scratch paths and open-file observations. The previous build is a superseded duplicate eligible for the coordinator's recoverable cleanup after that evidence is frozen; the final build remains available for unfinished integration. Small duplicated run folders can also be moved after verifying their evidence copies. No cleanup was executed by this agent, no physical space recovery is claimed, and no production data or prior-stage evidence was touched.
