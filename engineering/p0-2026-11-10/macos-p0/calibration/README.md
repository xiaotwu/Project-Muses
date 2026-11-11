# Acoustic calibration preparation

An AppKit calibration app has been built and ad-hoc signed, and **46 deterministic offline checks pass**. The build/test preparation did **not** launch the app, request microphone permission, record a device, or play sound. After that preparation, the root agent verified the final signature, launched the app, and observed its idle window with consent unchecked and no microphone request. The user then authorized one short environmental-audio check, which is owned by the root agent; its physical result is separate from this offline evidence. This is preparation for [validation protocol §5](../../contracts/validation-protocol.md), not a first-sound baseline result.

The retained app is:

```text
/Users/xiaotwu/.muses/tmp/p0-20261110-01/interop/macos-calibration/attempts/20261110T235039.849228Z/MusesAcousticCalibration.app
```

Its executable SHA-256 is `7184357322ede54435e316fc246e4fa84a527be45d6503c9f06ae9db439d5dfa`. The complete source/build/receipt hashes are in [evidence](evidence/summary.json) and the [frozen file manifest](source-hashes.json). The GUI uses the system AppKit controls; its launch code stays idle and creates no audio engine, tap, capture timer, or permission request.

## Consent and lifecycle

The root agent obtained the user's explicit permission before its separate environmental-audio check. This handoff's tests remain offline. The visible app requires both the explanatory consent checkbox and **“开始短时校准”**. Only that action can request microphone access. A granted permission callback must still match the current atomic operation generation before audio starts; a cancelled or closed operation cannot restart from a late callback.

The helper accepts only built-in input and output devices. It leaves device selection, volume, mute, and system settings unchanged. Two different, original, finite nonperiodic markers are submitted at source-frame offsets 0.5 s and 3.0 s; each lasts 160 ms. The generated waveform's mathematical peak bound is 0.16 of full scale and its approximate RMS is 0.02; actual acoustic loudness depends on the user's existing output setting. The normal capture stops at about 6 seconds. Callback checks independently prohibit further sample submission/copying at 8 seconds. The controller requests an engine stop on its 100 ms watchdog, cancellation, close, minimize, sleep, or audio-configuration change.

The **8-second hard guard applies to this tool's callbacks**, not a proven upper bound on AVAudioEngine/driver shutdown or hardware-buffer drain. Actual stop latency must be checked in the first permitted device run. Cancellation blocks further source frames in bounded render-loop increments and stops recording storage; an already queued device buffer can have a tail. The control queue tears down the engine/tap before analyzing the owned recording buffers. Analysis is cancellable. A cancellation before the atomic result-completion point can only publish `measurement_invalid`/`cancelled`, never a matching result. A later Cancel after completion is a no-op.

No raw recording is written to disk. Owned capture and downsample buffers are explicitly cleared. This does not claim erasure of AVAudioEngine or operating-system buffer copies. The owned PCM/reference/analysis reservation is capped at **8 MiB**, including a bounded callback-buffer allowance. This is not a cap on all framework allocations or GUI process RSS, neither of which has been measured. Input rates outside 16–192 kHz, unsupported channel/format shapes, oversized callbacks, lost capture locking, invalid timestamps, clipping, or route/gain changes fail the measurement.

## What a future receipt means

Each marker records three separate points on the Mach host-time axis:

1. The source-render reference timestamp reported by the audio callback, plus its frame offset.
2. The monotonic time when the source callback first writes a nonzero marker sample into its supplied buffer. This is **before the mixer and hardware**, not physical speaker onset.
3. The microphone's matching-reference and sustained-onset timestamps, derived from capture sample positions and a fitted capture clock.

The receipt keeps the click event's raw timestamp and the application's handler timestamp, input/output sample rates, built-in route labels, readable device volume/mute/buffer/latency values, unknown fields as null, clock drift and maximum fit residual, noise/clipping measures, match scores, and typed failure reason. It also embeds the source-set hash from the signed app's Info.plist. Persistent device UIDs are not read. Unknown or external route names are not exported as personal device names.

Hardware-reported latency is preserved as a diagnostic and is not silently subtracted. `detector_resolution_and_clock_residual_ms` combines the frozen 2 ms onset window, sampling resolution, and measured clock-fit residual. It is **not** a total physical error bound. `total_physical_error_bound_ms` remains null: a single speaker-to-microphone check cannot separate fixed device timestamp bias, DAC/speaker delay, propagation, and ADC delay. Two matching markers demonstrate only the observed acoustic path and its match quality. They do not establish absolute first-speaker-onset accuracy or eliminate a fixed clock bias.

The receipt's confidence class is a deterministic detector classification, not a statistical probability. This tool does not emit `L_sound`, percentiles, or a baseline attempt. **Do not use these synthetic or single-run fields to fill campaign `max_clock_error_ms` / `max_capture_error_ms` automatically.** A trustworthy total-error decision and the event-clock mapping still require the physical measurement review. The ≥30-source / ≥100-attempt campaign remains separate.

## Frozen detector and offline results

Detector version: `acoustic-chain-v1`. Source and parameters were fixed before any physical test:

- Original 32-component finite waveforms occupy 550–2342 Hz with 5 ms edge envelopes. The two phase/frequency sets differ and are never repeated in a run.
- Linear resampling to 6 kHz is deliberately limited to this known marker detector, not general music processing. High-frequency environmental noise may reduce confidence; inadequate signal is rejected.
- Absolute normalized correlation ≥0.65 for both markers; best/runner-up ratio ≥1.6, with a ±10 ms exclusion around the best match; correct marker separation within 20 ms.
- Initial 250 ms noise window; signal RMS ≥max(0.0001, five times measured noise RMS). Onset requires three consecutive 2 ms windows above the frozen threshold.
- Clip fraction ≤0.5%; at least four clock anchors spanning ≥2 s; monotonic frame/time sequence; per-anchor continuity ≤3 ms, fit residual ≤1 ms, fitted rate drift ≤2000 ppm. Unsupported or ambiguous input produces a typed invalid result.

The final offline executable passed 46 checks in about 1.4 seconds with maximum RSS **7,913,472 B**. Eleven positive synthetic cases cover known delays, 16/44.1/48/96/192 kHz capture, 44.1↔48 kHz conversion, low gain, noise, weak echo, inverted polarity, and a known 150 ppm clock drift. Their maximum reference-position error was **50 μs** and minimum normalized match score 0.886482. These are fixture results, not physical precision claims; the corresponding detector resolution components were approximately 2.18–2.23 ms.

Negative checks cover silence, noise-only input, wrong/missing/duplicated markers, incorrect spacing, insufficient signal-to-noise, excessive duration/rate, nonfinite PCM, clipping, missing/backward/discontinuous clocks, and excessive drift. Lifecycle checks cover permission cancellation, late generation rejection, BUSY, fresh operation recovery, cancellation during correlation, the timer-read → cancel → finish race, and the result's atomic completion point. The offline executable links no AVFoundation, AVFAudio, or CoreAudio device API; the app is built/signature-verified but never executed by the test runner.

## Review, failed attempts, and physical prerequisites

The first compile failed because `explicit_bzero` was unavailable in this SDK. It was replaced with a portable volatile-byte wipe; the failed receipt and compiler error remain in evidence. A 42-check predecessor and a 44-check predecessor passed their then-current tests. Independent review found that the latter could turn CANCELLED back into FINISHING, allowing a cancelled run to be reported as matched. Its source snapshot and built bytes remain preserved as superseded evidence. The final gate rejects that transition; two additional deterministic regressions pass. These older successful builds are **not** the candidate to run.

Before a physical run, confirm the user's explicit consent, built-in speaker/microphone routing, a comfortable audible volume, stable device placement, quiet surroundings, and no unrelated active playback. Observe the permission dialog and idle/start/cancel/close behavior. Check the actual sample rates, all route/latency unknowns, capture timestamp continuity, elapsed capture and device-stop behavior, waveform detectability, and absence of a saved audio file. If any timing or route assumption cannot be supported, retain `measurement_invalid` or the unresolved error bound. Do not retune thresholds after observing a fast/slow result without creating a new detector version and preserving the old attempt.

The receipt store is limited to 32 JSON files of at most 64 KiB each in the owned scratch `receipts/` directory. It stores no PCM and does not evict old receipts automatically. A full store prevents another capture. A 40 GiB free-space floor is checked before capture and before saving a summary. The build's whole scratch cap is 64 MiB; [inventory](evidence/scratch-inventory.json) distinguishes the current app from superseded attempts and completed test helpers. The first freeze attempt correctly refused to claim zero handles because the root had begun its authorized UI check; its failed receipt is preserved. The current app is retained for that check, and the active runtime receipt subtree is excluded from immutable preparation inventory. No cleanup was performed here. Registration, preferences, permission state, and physical-result cleanup arising from the root's later launch belong to its separate final inventory.

Build and offline verification, from the P0 worktree:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation interop --timeout 120 -- python3 engineering/p0-2026-11-10/macos-p0/calibration/build_offline.py
```

The build script deliberately has no run/record mode. It follows the shell-first macOS build workflow while preserving the explicit no-launch boundary. It changes no product repository, root Run action, or signing identity. Signing is ad hoc with the audio-input entitlement and no timestamp service; notarization is not claimed.

Apple documents the distinction between host/sample representations in [AVAudioTime](https://developer.apple.com/documentation/avfaudio/avaudiotime) and describes [outputPresentationLatency](https://developer.apple.com/documentation/avfaudio/avaudionode/outputpresentationlatency) as downstream render latency. Those API properties are not evidence that a speaker emitted sound. The runtime path still needs the permitted acoustic check.
