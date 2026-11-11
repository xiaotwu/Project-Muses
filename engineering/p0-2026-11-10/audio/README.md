# P0 native audio feasibility — 2026-11-10

The independent FFmpeg + miniaudio route is technically viable on macOS for
the tested AAC/M4A and Opus/WebM inputs. The same decoder and native-output
bridge compile for iOS arm64. This is a bounded engineering proof, not a
production player, a completed iOS runtime gate, or an audibility claim.

The Muses/BitChord implementation was not copied. The harness source here is
MIT. FFmpeg retains its own LGPL license; miniaudio uses its MIT option.

## What ran

| Check | Observed result |
| --- | --- |
| Fresh FFmpeg build | 8.0; configure reports LGPL 2.1 or later; GPL, version3, nonfree and external autodetection disabled |
| Minimal runtime components | avformat, avcodec, avutil, swresample; AAC/Opus decoders, MOV/Matroska demuxers, file/HTTP/TCP; no encoders, external libraries or video |
| Native output | miniaudio 0.11.26 CoreAudio, shared output, float stereo 48 kHz, requested 256-frame period |
| Decode | Both generated four-second fixtures produced 192,000 frames; local and throttled loopback HTTP passed |
| Seek to 1.5 seconds | AAC: zero-frame offset, RMS difference 0.0000069. Opus: measured −24-frame (−0.5 ms) alignment from millisecond WebM timestamps; aligned RMS difference 0.0000546 |
| Preparation and two-input pool | Each input is a fixed 32,768-frame stereo float SPSC ring. Combined PCM reservoir is 524,288 bytes, plus fixed 65,536-byte conversion scratch per decoder |
| Gapless scheduling | 384,000 output frames, zero observed underflows/clips, no silent 10 ms transition window |
| Equal-power crossfade | 336,000 output frames, zero observed underflows/clips, minimum 10 ms RMS 0.0585880 |
| Cancel blocked HTTP | 97.535 ms after cancellation request; cancelled generation produced no PCM; replacement decoded normally |
| Cancel full ring | Producer stopped at the 32,768-frame limit; old decoder cannot enter the replacement ring |
| Native stop/resume | 96 callbacks, 24,576 frames, two started and two stopped notifications; clock stayed fixed while stopped |
| Prepare next after playback starts | Next initially had zero decoded frames; later preparation scheduled one native transition; 322 callbacks, 82,432 output frames, zero observed underflows |
| Adversarial concurrency | 1,000,000 SPSC frames preserved order and capacity; starvation produced silence; failed next preparation left first input intact; watchdog stopped output |
| ThreadSanitizer | Instrumented harness and miniaudio passed the adversarial run with exit 0 and no reported race; prebuilt FFmpeg archives were not instrumented |
| Apple linking/signing | Explicit frameworks; no `dlopen`/`dlsym`/`dlclose` imports. Ad-hoc hardened-runtime executable passed strict signature validation and the full test suite, with no additional entitlements |
| iOS build | arm64 iOS 17 deployment target, iOS 27.2 SDK; both bridge objects and four FFmpeg archives compile. Runtime evidence belongs to the root/source agent's physical-device harness |

All native output runs by this audio agent were **muted**. A functioning callback,
nonzero decoded PCM, and a running output clock do not prove that a person heard
audio. Physical routing, interruptions, lock-screen/background execution and
human audibility remain separate gates. No system volume or output route was
changed. No personal audio, credentials, library records or installed app was
used by this slice.

## Persistent iOS integration

`p0_audio.h` supplies a small C ABI to the native source-validation host:

1. The host owns AVAudioSession category and activation. Use playback plus
   mix-with-others for the isolated probe. miniaudio is configured with
   category `none`, no activation and no deactivation.
2. `muses_p0_audio_start` prepares only the first input and starts exactly one
   native output. A watchdog bounds the session to at most 180 seconds.
3. After the host freshly resolves/downloads the next item, `prepare_next`
   creates the second decoder. The crossfade is scheduled relative to the
   running output clock only after that decoder is ready.
4. `snapshot` exposes numeric callback/clock/decoder/consumption/transition
   counters. `nonzero_output_frames` counts actual samples after the mute and
   app-gain stages, avoiding a false pass from clocks advancing through silence.
5. `stop` stops output before decoder cancellation/join/destruction. Control
   operations are serial and off the UI/audio thread; snapshot must not overlap
   destruction. P0 permits one next item per session.

`audible=0` produces zeros. `audible=1` sends decoded media with 0.12 app gain;
the coordinating agent must arrange the physical test. Neither setting changes
system volume. The bridge accepts complete task-owned media files. The minimal
FFmpeg build has no HTTPS/TLS implementation: real HTTPS download/credentials
stay in the native URLSession host. Progressive native HTTP-to-AVIO integration
is future work; a complete downloaded file is not evidence of that feature.

The iOS artifact handed to the source agent is `audio-probe.o`, SHA-256
`324b4b09fc763d3bc5733b334670522d5d0a8160706cf580a7898221ee872c12`.
`miniaudio-backend.o` is
`6e346b04baf3b7519e3d4e56a87679e8742b24404698417ac629c9fc3c4ac285`.
Link those with the four FFmpeg static archives, libc++, CoreFoundation,
CoreAudio, AudioToolbox, AVFoundation and Foundation. Full artifact hashes are
in `evidence/artifact-manifest.json`.

## Findings carried into implementation

- Decoder PTS must use the stream packet time base and the decoder-adjusted
  frame PTS, including skip samples/priming. A 120 ms warm-up seek removed the
  AAC overlap-history error. WebM's timestamp quantization still requires an
  explicit seek tolerance, measured here as 0.5 ms.
- AVFoundation and FFmpeg both declare `AVMediaType`. Keep native output in a
  separate Objective-C++ translation unit; keep decoder code in C/C++.
- A source-tree file named `version` shadows libc++'s `<version>` if FFmpeg's
  source root is placed first in the include path. Use `-idirafter` or properly
  installed public headers.
- FFmpeg 8.0 emits an Opus parser diagnostic at EOF on this generated WebM.
  All 192,000 decoded frames, seek/transition checks and decoder return codes
  still pass. The raw diagnostic is retained. Source inspection points to the
  complete-frame parser's empty-flush path; this explanation has not been
  proven with a debugger. It must be resolved against a reviewed release pin
  before production adoption, rather than hidden by log filtering.
- Shared float mixing is not bit-perfect output. Normal output, exclusive or
  bit-perfect modes, DSP, loudness, time stretching and AutoMix need distinct
  implementation and acceptance. This proof does not claim them.
- This harness does not implement production underrun recovery, arbitrary
  queue replacement, source-expiration retry, device reroute/interruption
  recovery, metadata/probe/packet memory caps or persistent downloads/cache
  management. It demonstrates the required primitives and ownership order.
- Static linking was used for the isolated proof. Shipping LGPL components
  needs retained notices, corresponding source/build instructions and a
  verified relink/replace pathway. Ad-hoc hardened runtime is not Developer ID
  signing, notarization or a release-compliance conclusion. The production
  version/security review and packaging decision remain open.

## Reproduce

All commands must be invoked through the frozen guard. From the P0 worktree,
run each command independently, replacing `ACTION` with `bootstrap`, `fixtures`,
`macosx`, then `iphoneos`:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- \
  python3 engineering/p0-2026-11-10/audio/build.py ACTION
```

Then run `audio/run_tests.py` and `audio/build_stress.py` through the same guard.
The default tests are silent. `collect_evidence.py` copies bounded logs/hashes
only. It does not archive compiler output. No global installation is performed.

`source-lock.json` pins the official FFmpeg archive and miniaudio header before
compilation. The pre-existing Homebrew FFmpeg 9.0.2 contains GPL components; it
was used **only** to encode generated sine fixtures. Its configuration is kept
in `evidence/fixture-generator.txt`; it is not linked or distributed as the
selected decoder. Fixture commands, sizes and hashes are reproducible and
recorded. This test does not consume BitChord implementation code.

## Evidence and disk disposition

`evidence/final-run/` contains the successful hardened-runtime run.
`thread-sanitizer.log`, signature/framework records and source/fixture/artifact
manifests are retained. Failed first-run output, failed compiler logs and guard
receipts remain visible; successful retries did not erase them. The bounded
evidence snapshot is bounded below 150 KiB.

Audio scratch high-water during the full audio test was **151,961,600 bytes (144.92 MiB)**,
within the 1.25 GiB allocation. `scratch-inventory.json` distinguishes logical
sizes from allocated blocks and records actual filesystem free space. The
observed shared free-space increase is not attributed to this audio task.

No scratch has been irreversibly deleted and no audio-owned Trash has been
created. Space recovered by this slice is **0 bytes**. The iOS objects, archives
and fixtures remain active dependencies of the physical-device probe. After the
root records that probe's result, all of this exact scratch subtree can be
inventoried for recoverable cleanup:

`/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio`

The extracted sources (~111.45 MiB allocated), archive (~11.12 MiB), macOS and
stress build outputs are reproducible scratch, not an evidence archive. A
9,978-byte generated Python bytecode file was moved out of the worktree into
`audio/superseded-python-bytecode/` for the same recoverable cleanup; subsequent
helper runs disable bytecode output. The
root must check active processes/open files before moving them to the task's
dedicated Trash. No cleanup permission blocker was encountered by this slice.

## Primary references

- [FFmpeg 8.0 license](https://github.com/FFmpeg/FFmpeg/blob/n8.0/LICENSE.md)
- [FFmpeg decoder example](https://ffmpeg.org/doxygen/8.0/decode_audio_8c-example.html)
- [miniaudio 0.11.26 release](https://github.com/mackron/miniaudio/releases/tag/0.11.26)
- [Pinned miniaudio header, license and Apple linking instructions](https://github.com/mackron/miniaudio/blob/0.11.26/miniaudio.h)
- [miniaudio manual](https://miniaud.io/docs/manual/index.html)

Context7's `/mackron/miniaudio` documentation was also consulted for native
notifications, iOS session ownership and runtime-linking configuration.
