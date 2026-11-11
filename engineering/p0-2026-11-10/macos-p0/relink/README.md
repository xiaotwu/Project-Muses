# macOS static LGPL relink proof

Result: **passed for the independent P0 prototype**, using the exact FFmpeg 8.0 source, one frozen application object and one frozen miniaudio object. No production application, existing dependency installation or previous evidence was changed. No download or phone operation occurred.

The successful attempt is `/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-relink/attempt-20261110-232515`. The bounded evidence and minimum retained input index are in `evidence/manifest.json` and `evidence/package-index.json`.

## What was actually replaced

1. Copy and hash-check the retained FFmpeg release archive, miniaudio header, original MIT P0 source and generated AAC/Opus fixtures into new active scratch. Extract the archive there; never build or execute inside Trash.
2. Rebuild all four selected FFmpeg static libraries from source, with the original configure flags. The rebuilt `avformat`, `avcodec`, `swresample` and `avutil` archives **all matched the earlier frozen library hashes byte for byte**. This was a real compile, not a relink of recovered libraries.
3. Compile unchanged `probe.cpp` and `backend.mm` once, with `-fno-lto`, and freeze `app.o` and `miniaudio-backend.o`. Link the stock prototype from those objects and the freshly rebuilt libraries.
4. Change only `libavutil/version.c`: `av_version_info()` appends `+muses-p0-relink-1`. Rebuild `libavutil.a` from that modified source and link the **same unchanged application and miniaudio objects** with the replacement archive. The other three libraries are also unchanged. `replacement.patch` preserves the exact edit.
5. Ad-hoc sign both standalone Mach-O prototypes with hardened runtime and no additional entitlements. Strict signature verification and execution pass. The replacement program prints `8.0+muses-p0-relink-1`; both its archive member and executable hashes differ from stock.

The marker is an intentionally small observable library modification. It proves replacement of a source-built LGPL component, not a decoder improvement or compatibility with arbitrary future ABI changes.

| Identity | SHA-256 |
| --- | --- |
| Same application object in both links | `46d3624653947cbd2478308f90322264c1c4da4452831234cd6f63c29b2fe7a8` |
| Same miniaudio object in both links | `cd2a842f4ca3bcdf58c60c4545883cd72b7413382e8133e063f4ff8340ceea80` |
| Stock `libavutil.a` | `98ad0cbf1520bc1e9b015f16eb830f688f9d77852ecfd6d7163f77e3ad5a83d3` |
| Replacement `libavutil.a` | `e9519ebd23a0e7d9f96ca5f3f25b1c97a92b3e92434f4e18c3751bb464772366` |
| Signed stock prototype | `01762239629a18f22e9facec626e523f0cb8d83da4efb503eb18ad55a2215976` |
| Signed replacement prototype | `19c3d3a7bd1ff8dbfe30cfed3a0b2e11308e7a7b9ac1168b6dfca15f687bda63` |

`link-manifest.json` also records unsigned hashes, each library hash, the changed `version.o` archive-member hashes and exact link arguments. Inspection confirms static FFmpeg linkage and no `dlopen`/`dlsym` imports; Apple system frameworks remain dynamic platform dependencies.

## Configuration and minimum retained inputs

FFmpeg uses `--disable-everything --disable-autodetect --disable-gpl --disable-version3 --disable-nonfree`, with AAC/Opus decoders and parsers, MOV/Matroska demuxers, file/HTTP/TCP protocols, the four selected libraries, pthreads and static linkage. Programs, docs, debug, avdevice, avfilter and swscale are disabled. No external codec library or Homebrew binary is linked. The exact command and generated `config.h`, `config_components.h`, `ffbuild/config.mak` are retained. The configuration and runtime license functions report `LGPL version 2.1 or later`.

| Category | Retained input |
| --- | --- |
| Source | Exact FFmpeg archive, exact miniaudio header, unchanged application sources, two generated fixtures, and the replacement patch |
| Configuration | Configure command, generated configuration and complete toolchain versions |
| Objects | `objects/app.o`, `objects/miniaudio-backend.o`, and their frozen hashes |
| Libraries/link | Four freshly rebuilt stock archives, replacement `libavutil.a`, exact link commands, and signing commands/logs |
| Notices | FFmpeg license overview and LGPL 2.1 text, complete miniaudio license tail, original project MIT text, and experiment notices |
| Results | Both signed prototypes, regression output, signature/link inspection, guard receipt, execution lock and journal |

The exact miniaudio header calls its selected alternative **“MIT No Attribution”** (alternative 2). Its original full license text is retained; the older coarse `MIT OR Unlicense` source-lock label was not rewritten. The application source remains under its original MIT notice. The SDK/toolchain are platform prerequisites and are not copied into the kit.

For this technical prototype, a replacement library can be linked using the recorded command with only its library path and output path changed; application objects do not need recompilation. The complete FFmpeg source archive and configure command remain available after removing expanded compiler work. Reconstructing that tree from the archive and applying `replacement.patch` reproduces the source edit.

## Regression evidence

Stock and replacement AAC/Opus tests passed with identical decoded/seek/mixer metrics. Both decode the 4-second fixtures to 192,000 frames. A 1.5-second seek yields 120,000 AAC frames and 120,024 Opus frames. Opus retains the previously observed −24-frame alignment for this fixture; this is not a universal seek bound or a newly proved explanation of timestamp quantization.

The equal-power crossfade and gapless tests use two bounded PCM rings totalling 524,288 bytes and one clock, with zero underruns or clipping. The replacement's shared CoreAudio session was **muted**: next decoder initially absent, one delayed transition, 319 callbacks / 81,664 clock frames, zero underruns. This does not establish human audibility, first-real-sound latency or long-run reliability. No system route or volume was changed.

The known Opus packet-header message appears in both successful regression logs and is preserved. This experiment neither fixes nor hides that diagnostic. There were no failed build/test stages in this attempt.

Toolchain: Apple clang 21.0.0 (`clang-2100.4.1.1`), Xcode 27.2 (`27B52`), macOS SDK 27.2, linker 27106.1, deployment target arm64 macOS 26.0; host macOS 27.2 (`26B123`). Signing is ad hoc with `adhoc,runtime` flags; no Team ID, Developer ID signing, notarization or product distribution is claimed.

## Reproduction and hygiene

The plan and script hashes were frozen before execution. All generation ran through the original guard:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation audio -- python3 engineering/p0-2026-11-10/macos-p0/relink/run.py --plan-sha ca860bbbe87b0af4cb9574d844fbefcd47d02585870881fc593c0a3d3e196423 --script-sha 0d835613db8ee10324bee6d9bc8c29ddb97e07ed7af7f40fa86bd564f916dc0c
```

The script uses the exact retained archive and creates a new attempt rather than overwriting earlier failures. It refuses another attempt without room under the 384 MiB subbudget. Peak observed scratch allocation was 145,424,384 bytes; completed allocation was 145,461,248 bytes. The expanded `work/` tree is 120,979,456 allocated bytes and is eligible for coordinator recoverable cleanup after frozen inventory and open-file verification. The approximately 24.5 MB remainder is the minimum retained kit and evidence, not a compiler cache archive. No space has been reclaimed by this agent, and no files have been irreversibly disposed of.

This proves a source-rebuild/object-relink/ad-hoc-run path for the P0 CLI prototype. Shipping-library selection, final application packaging, corresponding-source/relink materials for an actual release, Developer ID re-signing/notarization, and legal review of the intended distribution remain separate work. It is not a finding that the product has completed its LGPL distribution obligations.
