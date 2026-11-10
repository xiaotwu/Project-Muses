# P0 v2 native transport and decoder bridge

This slice supplies a native, bounded media path to the source/parser host.
JavaScript supplies a small descriptor; media bytes stay in URLSession, one
native read block, the owned partial file or FFmpeg's native AVIO path. It does
not solve an upstream 403, claim a complete live-source transfer, implement
HLS/SABR, or open an audio output device. Root owns live public-source testing
and the parser-memory work. No phone operation was performed by this slice.

## Interfaces ready for integration

`muses_transport.h` / `NativeTransport.m` expose a C ABI callable from an
Objective-C host:

- `mt_create`: copies URL and bounded public headers into native memory;
  requires the host's existing URL authorization callback. Production requires
  HTTPS. Loopback HTTP works only in the separately compiled `MT_TESTING` test
  binary. No signed URL, credential, raw NSError or response body is logged.
- `mt_read_at`: pulls one bounded block, validates its Content-Range, supports
  byte-offset seek, and copies into caller-owned storage. There is one active
  request and no speculative media prefetch.
- `mt_copy_to_file`: owns the handle's control lock for the whole copy, writes
  a mode-0600 `.partial`, and publishes the destination only after every byte
  in `[0,total)` has been validated, written and fsynced. Commit refuses to
  replace an existing file. A failure retains partial evidence and never names
  it as a complete file. Full crash-durable download/resume is not implemented.
- `mt_cancel` and `mt_snapshot`: remain usable during a read/copy. Progress
  callbacks run synchronously on the copying thread; blocking them stops new
  requests. Reentrant or concurrent public reads/copies return `MT_BUSY`.
  Destruction requires the host to cancel/join its worker first.

Call read/copy/decoder operations off the UI and real-time audio threads. The
host owns the exact isolated destination directory and serial handle lifetime.
Partial files are not reusable full-file inputs; a fresh attempt uses another
owned destination or an explicitly reviewed recovery procedure.

`muses_decode_probe.h` / `DecodeProbe.cpp` add
`md_compare_native_to_file(handle, complete_file, limits, report)`. This is a
P0 diagnostic helper, not a playback engine. It:

1. Verifies the complete local file is regular, nonempty, at most 16 MiB, and
   matches the validated native representation length.
2. Decodes AAC or Opus locally, then through native AVIO, for a full decode or
   a requested seek such as 30 seconds. Use a fresh native handle per call so
   full and seek checks each keep their own transfer budget.
3. Converts incrementally to stereo float at 48 kHz using a fixed 64 KiB
   conversion buffer; returns frame counts, source rate/channels, nonzero
   sample count, RMS, PCM SHA-256 and numeric errors. It never returns raw PCM
   or a URL to JavaScript and does not retain a whole decoded song.
4. Requires positive decoded frames and compares PCM hashes with the same
   decoder's local reference. A seek beyond EOF is a failure. Limits permit at
   most 900 seconds of decoded output and a 60-second per-pass watchdog; native
   cancellation is requested on timeout.

Canonical PCM equality proves agreement of these two byte delivery paths. It
is not independent decoding ground truth, sample-accurate seek validation for
every recording, audible playback, or a Mac 0.6.3 performance baseline. The
helper suppresses raw FFmpeg string diagnostics in this isolated process to
avoid accidental path/URL disclosure; numeric errors remain in the report.
The original FFmpeg 8.0 Opus EOF warning is retained in the immutable audio
evidence and in the earlier AVIO fixture run; it is not claimed resolved.

## Bounds and protocol behavior

| Boundary | Enforced behavior |
| --- | --- |
| Media representation | At most 16 MiB; any nonzero `content_length_hint` is a fixed expected total, checked against the first and subsequent responses |
| Native delivery budget | At most 16 MiB per handle; refetches count. Requested end offsets are clamped to the remaining budget. Malformed excess data triggers cancellation before cache append; this is not a claim to meter all TLS/wire traffic |
| Read block | 4–256 KiB, one application buffer and one request in flight; tests use 64 KiB or 4 KiB |
| Requests/time | At most 512 requests, each configured for 100–15,000 ms; no application retry loop |
| Descriptor | URL at most 16 KiB; at most eight public headers, at most 4 KiB combined; Cookie/Authorization excluded |
| Public headers | Preserve bounded User-Agent, Accept, Accept-Language, Origin, Referer and DNT, including upstream `DNT: ?1`; the bridge does not rewrite query parameters |
| RSS | Required `process_rss_limit_bytes`, at most 256 MiB. Local tests use 128 MiB; root integration may use 256 MiB. This samples whole-process RSS and cancels on an observed breach; it is not a hard allocator limit or a claim about unobserved peaks |
| Range validation | Exact requested start; end within requested bounds; finite consistent total; body/Content-Length agreement; identity Content-Encoding. Invalid or incomplete blocks never add validated progress |
| Progress | Union of completed byte intervals, so cached/overlapping reads do not inflate unique progress. Delivered and received byte counts remain separate |
| Representation changes | Total or ETag changes fail. A strong ETag is used with If-Range. A 200 response after validator-based range access fails closed. Without a server validator, length/range checks alone cannot prove unchanged bytes across requests |
| Ignored Range | A complete response that fits the first native block can be accepted; larger 200 responses or nonzero-offset 200 responses are `range_unsupported`. A separate bounded sequential adapter is not implemented |
| Expiration | Known descriptor expiry yields `url_expired` / fresh-descriptor directive. A 403 with unknown/not-yet-elapsed expiry remains `http_forbidden`; there is no blind retry or inference that every 403 means expiration |
| Redirect/auth | Redirect targets still pass the host policy, but following redirects is not an implemented transport capability. Non-server-trust authentication challenges fail without credential prompts |
| Direct/HLS/SABR | Only declared direct representations are supported. Declared HLS and SABR return `kind_unsupported` before networking; no manifest/segment/Ump/SABR behavior is simulated |

## Observed local results

All requests from this slice went to task-owned servers bound to `127.0.0.1`.
The deterministic 262,144-byte transport fixture has SHA-256
`d30eb241f95e7c37c033251a78eae1610ac9b02dc99625442158180d35818c1b`.

| Test | Observed result |
| --- | --- |
| Complete transfer | Four validated ranges, 262,144 unique bytes, committed file byte-for-byte equal to fixture, same SHA-256 |
| Cached/backward reads | Duplicate read caused no request or progress increase; overlapping ranges yielded 66,536 unique bytes from 131,072 received bytes |
| Backpressure/control ownership | Blocking progress for 150 ms caused no further requests; a public read inside the callback returned BUSY |
| Wrong range/ETag change/declared-length mismatch | Typed rejection; no complete file |
| Ignored Range/oversize representation | Rejected before media delivery |
| Mid-file 403 | Exactly 65,536 validated bytes remain in `.partial`; final destination absent |
| Truncated body | No completed interval or delivered block; typed network/truncation failure |
| Cancellation | 0.448 ms observed in the latest loopback run; this is one local observation, not an Internet or device SLA |
| Network/request caps | 70,000-byte budget ended at exactly 70,000 received bytes; one-request budget prevented a second request |
| Known expired descriptor | Zero HTTP requests; fresh-descriptor directive |
| Public header preservation | Upstream public headers, including `DNT: ?1`, reached the controlled server |
| Native AVIO AAC | Full 192,000 frames, seek 120,000 frames; PCM exactly equal to local decode; 13 range requests; 4 KiB native cache |
| Native AVIO Opus | Full 192,000 frames, seek 120,024 frames; PCM exactly equal to local decode; 17 full / 25 seek requests; 4 KiB native cache |
| Generic helper | Full and 1.5-second seek comparisons passed both frozen fixtures; full AAC RMS 0.062338426, Opus RMS 0.062541218; bounded counts/RMS/hash output only |
| Beyond original fixture assumptions | New owned 40-second AAC at 44.1 kHz: 1,920,000 canonical full frames / 480,000 after 30-second seek. Opus at 48 kHz: 1,920,000 / 480,024. All four PCM hashes match local reference; observed RSS at most 16,973,824 bytes |
| Observed RSS | Latest transport run at most 15,155,200 bytes at measurement points; AVIO fixture run 21,397,504; generic helper 16,433,152. These are sampled values, not kernel-enforced ceilings |

The two audio fixture hashes and the precise scope of the Opus −24-frame
alignment result remain in the original audio report and
`contracts/validation-protocol.md`. That one 0.5 ms observation is not a
universal quantization guarantee. Real public media remains the coordinating
host's separate test, using the generic helper. The new synthetic 30-second
seeks establish helper behavior, not a claim that any live-source
representation was successfully transferred.

## Current integration artifacts

Objects are in the active scratch root
`/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport`:

| Object | SHA-256 |
| --- | --- |
| `macosx/NativeTransport.o` | `f57aaa6a5ec0fb4950227281bb1475f5251c3e02b662774b602b0d3ed4fc31fc` |
| `iphoneos/NativeTransport.o` | `a46054d165c69d91ee67a7113c613d682365bcb719a59e9ac993524c7e54e8a2` |
| `macosx/DecodeProbe.o` | `3cf1a28644a3ff6744808014673c8c2ea144d73c283eb6761f5132d7b8d01e1d` |
| `iphoneos/DecodeProbe.o` | `88999422803d02594e0b66f20ced68bd1c7feafc981514e15f0b7c47c70cd10d` |

Link the transport with Foundation. The decoder helper additionally needs
libc++ and the four already-proven FFmpeg 8.0 LGPL archives (avformat, avcodec,
swresample, avutil); CommonCrypto is system-provided. iOS objects target arm64
iOS 17 with the installed iOS 27.2 SDK. Cross-compilation is not device evidence.

Run `run_local.py`, `run_avio.py`, `build_objects.py` and
`build_decode_probe.py` only through the original frozen
`run_guarded.py --allocation source`. The source-wide 1 GiB budget applies in
addition to this slice's 200 MiB allocation and the 40 GiB free-space floor.
Scripts never install dependencies globally. Original `audio/` and `source/`
code/evidence were not edited.

## Provenance, failed attempt and cleanup handoff

The macOS decoder archives and frozen audio fixtures were copied out of the
previous recoverable Trash into active scratch, with their original hashes
verified. No executable or library was run from Trash. Only public FFmpeg
headers plus generated `avconfig.h` are now active; total selected input bytes
are 4,105,636. The macOS and retained iOS generated header hashes match:
`975611ad5eba15212d9e1d5fca9d4fdf0daec6d2269b2fcab8e29af8667164bc`.

The first copy included unnecessary private headers and failed its own 8 MiB
assertion. That failed guard receipt is retained. A subsequent correction was
frozen by script and plan hashes, checked for open files, and moved 711 unused
copied headers to this slice's recoverable directory:

`source/v2-transport/Trash/unused-private-headers`

The original prior-stage Trash was not modified. Correction plan SHA-256 is
`5cdd21d8bc5651d90d8e0d2164b77180cac2e3c637c0675d06ab1a313c2ae7cb`;
completed journal SHA-256 is
`eaa079e8de5841576573438f5982b29f8fc0175fe9d47740dc11dc12341e8431`.
The executable correction script was verified as
`2c9e6cc9fb23c8dce42183fdd1e99f67c62bda3b4f75710ef40fe108d684a672`.

At the recorded inventory, the correction Trash contains **7,953,601 logical
bytes / 9,486,336 allocated bytes**. The whole slice contains **21,463,040
allocated file bytes** (about 20.47 MiB), far below 200 MiB. Actual filesystem
free space was **574,520,111,104 bytes**; this shared observation is not credited
as space recovered by this slice. Recovered physical space: **0 bytes**.

Root is coordinating stage-end cleanup. Keep the four active production
objects, selected decoder inputs and all bounded evidence until its integration
ends. Earlier local test executables, duplicate generic-test executables,
generated fixture copies/partials and the 9 MiB correction Trash are owned,
explained scratch for recoverable cleanup after checking active processes/open
files. Failed receipts and the correction plan/journal remain evidence, not a
reason to retain compiler caches. No irreversible disposal or permission
blocker occurred in this slice.
