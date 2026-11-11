# macOS P0 status

P0 remains **in progress**. These are isolated backend and measurement tools;
the new backend is not integrated into the production Mac application. The user
has deferred the next iPhone run. No additional phone operation or microphone
capture was performed during this continuation.

## Completed continuation

- [Streaming v2](streaming-v2/README.md) separates normal decoder/resampler/ring
  completion from failure and cancellation, closes the seek publication race,
  and preserves a transport failure that precedes Stop. Seventeen local cases
  pass, including full short AAC/Opus, nonzero timeline origins, seek, delayed
  next input, and controlled failure/cancellation interleavings. The earlier
  successful short observations and later failures remain intact.
- One muted public **Opus/WebM** run produced PCM and supplied the output
  callback after 262,144 bytes. It read 333,050 bytes in two ranges, sought near
  the end, and reached normal EOF with an empty ring and released worker/handle.
  Its 3,775-frame tail matched the retained same-representation fresh-seek
  reference. Peak RSS was 87,080,960 bytes. The run accumulated 2,816 underflow
  frames (about 58.7 ms), without a per-phase breakdown; this is not a gapless result or continuous full-track
  playback. The run was silent and provides no physical first-sound measurement.
- All linked objects and static-library members have a deployment target at or
  below macOS 26 after rebuilding QuickJS and parser dependencies. Runtime
  evidence still comes from this macOS 27.2 host, not a macOS 26 device.
- [Baseline runtime preparation](baseline-runtime/README.md) audited the old
  application's new and legacy namespaces and its individual cache limits.
  Fifteen offline checks and real read-only preflight passed. An opt-in sampled
  supervisor is prepared with a 128 MiB runtime ceiling and an earlier stop
  threshold. It does not delete library data and is not a hard filesystem quota.
  The baseline app remains unlaunched.

The [first macOS checkpoint](README.md), [relink proof](relink/README.md),
[draft corpus/campaign](corpus/README.md), and their frozen manifests are retained
unchanged. The current index is separate so that their historical observations
can still be checked byte for byte.

## Remaining evidence

The [acoustic summaries](calibration/physical-evidence/PHYSICAL-RESULT.md) both
failed marker matching. The user first reported uncertainty and later reported
hearing two short beeps; neither report identifies a particular run. Hearing is
qualitative evidence, not a successful detector calibration. Total physical
timing error, actual first sound and the baseline/candidate comparison remain
unmeasured.

Corpus identity/audition, controlled performance samples, physical route changes,
the deferred iPhone transition, final distribution materials and production
integration remain open. Seek comparisons use stated codec/container references,
not a universal sample-accuracy guarantee. Quantized timing and unsupported
ambiguous metadata combinations are explicitly documented in the streaming
report. P1–P9 remain Backlog; no release or website was published.

[Stage 7 cleanup](cleanup/STAGE7.md) records recoverable retirement of the
completed test helpers and superseded streaming builds. The current validation
kit, paused calibration app, unlaunched baseline and deferred iPhone candidate
remain task-owned dependencies.
