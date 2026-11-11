# Isolated 0.6.3 runtime paths and sampled disk guard

The prepared baseline remains **unlaunched**. Its own cache policies do not
provide a total application cache limit. A separate, opt-in observer is ready
for a future empty acceptance session; only its read-only plan/preflight and
offline fixtures have run. No GUI, playback, recording, login, personal library
copy, credential read, cache deletion or system volume change occurred here.

## Source and identity

The audited release source is commit
`12260f050a374ee949053e8f63b039fe20f15148`, identified by the owning repository's
`docs/engineering/release-0.6.3.md`. The inspected checkout is
`/Users/xiaotwu/Code/Muses-Polyhymnia` at
`7ce577588f3a8fdd4b8f31fc9c01b541291ffdd3`; its entire `Sources` tree has no diff
from that release commit. The source hashes and the comparison are frozen in
[source-audit.json](evidence/source-audit.json).

The app is the [prepared metadata-isolated derivative](../baseline/README.md),
bundle `com.muses.acceptance.p0-baseline-20261110` (abbreviated **B** below), at
`/Users/xiaotwu/.muses/tmp/p0-20261110-01/interop/macos-baseline/Muses P0 Baseline.app`.
Its root authorities and automatic updates are disabled, but nested bundle
identities are intentionally unchanged. Full tree verification and strict nested
signature verification passed again during this task. That verifies the prepared
bytes; it does not establish runtime behavior.

## Exact writes and data classes

All paths below expand `~` to `/Users/xiaotwu` and `B` to the exact bundle above.
The source namespace selection is in
[MusesDataPaths.swift](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/MusesDataPaths.swift:7).

| Path | Class and evidence |
| --- | --- |
| `~/.muses/acceptance/B/data/` | Library truth. `muses-youtube-native.sqlite`, WAL/SHM and related store sidecars, upgrade snapshots and corrupt-store backups must be retained. [Store setup](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Persistence/MusesModelContainer.swift:5) and [failure backup](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Persistence/MusesModelContainer.swift:87). No library byte cap is asserted. |
| `~/.muses/acceptance/B/cache/` | Rebuildable application caches, detailed below. This directory is separate from library truth. |
| `~/.muses/acceptance/B/tmp/` | Future supervisor-owned `TMPDIR` for the app and inherited helpers. The product itself does not establish a total temp budget. This root has not been created. |
| `~/Library/Application Support/MusesAcceptance/B/` | Legacy library migration source. An existing SQLite store can seed the new store; the source is preserved. Refused when any unknown existing node is present. |
| `~/Library/Caches/MusesAcceptance/B/` | Legacy cache migration source. Product code can move or merge this directory and remove collisions/old directories; therefore the supervisor refuses any existing node. [Migration behavior](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/MusesDataPaths.swift:82). |
| `~/Library/Preferences/B.plist`, `~/Library/Preferences/ByHost/B.*.plist` | UserDefaults and possible host-specific preferences. Refused if already present; future matching files count against the runtime observation budget. They are not disposable library data. |
| `~/Library/HTTPStorages/B`, `~/Library/HTTPStorages/B.binarycookies`, `~/Library/Cookies/B.binarycookies`, `~/Library/WebKit/B`, `~/Library/Saved Application State/B.savedState` | Exact system-managed candidate paths, watched conservatively. Their future creation is not asserted merely from source. No inspection of stored values or deletion. |
| `~/Library/Caches/B` | Potential updater/framework cache. The updater can point it into `cache/updates/B`; only that exact symlink is accepted and its destination is already counted. [Updater paths](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Services/Update/UpdateTransactionStore.swift:79). |

`prepareRoot` sets the **shared** `~/.muses` mode to `0700` even for acceptance
bundles. Both it and `~/.muses/acceptance` already had the correct UID and `0700`
mode. Preflight checks them without modifying them; future supervision also
checks their inode identity. The main namespace, both migration roots, the seven
fixed system paths and all matching ByHost preferences were absent at preflight.

The acceptance Keychain service is `B.youtube.oauth`; the production service is
different. This audit did not query, copy or clear Keychain entries, Launch
Services, TCC, Spotlight or unified logs. Their absence and all possible
framework-managed filesystem writes are **not** established by this guard.
Nested updater registration and any later OS residue require a separate exact
cleanup review, using the original [nested identity receipt](../baseline/preparation-receipt.json).

## Actual cache limits

| Cache under `cache/` | Implemented limit | Boundary |
| --- | --- | --- |
| `streams` | Default 2 GiB; user choices 1/2/5/10 GiB. One family budget covers complete files, quarantine and reserved partials. | Per-source transfer maximum 512 MiB, 256 KiB chunks. This is not a budget for the other caches. [Budget](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/MediaCacheBudget.swift:4), [source limit](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/SharedStreamResource.swift:10). |
| `http` | URLCache disk capacity 64 MiB, memory 16 MiB. | Framework capacity setting, not a whole-app disk quota. [Startup](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/App/MusesApp.swift:52). |
| `ytdlp-search` | 64 MiB / 256 entries / 2 MiB entry. | Per-family total includes account/locale partitions and staging. |
| `home-feed` | 128 MiB / 512 entries / 2 MiB entry. | Same per-family contract. |
| `public-catalog/v2` | 200 MiB / 100 entries / 2 MiB entry. | Same per-family contract. [All three limits](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/RebuildableJSONCache.swift:4). |
| `lyrics/v2` | Entry strictly below 2,000,000 bytes; best-effort retain 100 JSON files after writing. | No strict total-byte admission policy; write/trim failures or unrelated files are not a total cap. [Implementation](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Services/Lyrics/LyricsDocumentCache.swift:20). |
| `artwork`, `waveforms` | No total-size limit in these cache implementations. | Potential paths, not a claim that each is exercised by the future session. [Artwork](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/ArtworkCache.swift:13), [waveform](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/WaveformCache.swift:9). |
| `stream-urls.json` | Legacy URL-only cache TTL 6 hours; no disk-byte/entry cap. | New typed stream descriptors instead use a separate volatile 128-entry cache. This is not evidence the public pipeline writes the legacy file. [Disk path](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/StreamURLCache.swift:20). |
| `yt-dlp`, `deno` | Explicit isolated locations, no aggregate cap in the host. | Acceptance passes `--ignore-config` and a cache directory; helper environment explicitly sets `DENO_DIR` and disables update checks. [Resolver](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/YTDlpBridge.swift:724), [environment](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Infrastructure/YTDlpRunner.swift:257). |
| `updates` | No relevant whole-app cap established here. | Empty feed/key prevents updater `start`; do not infer no framework state from that alone. [Configuration gate](/Users/xiaotwu/Code/Muses-Polyhymnia/Sources/Muses/Services/Update/UpdateService.swift:95). |

Public audio resolution uses an empty cookie argument list without consulting
configured cookie preferences. Metadata operations still have a cookie preference
path, so the future run starts from an empty acceptance preference domain and
must remain signed out. No browser-cookie consent, account import or personal
playlist is part of this baseline preparation.

## Prepared external observation policy

[budget.json](budget.json) sets a **128 MiB runtime ceiling** alongside the
768 MiB prepared-app subbudget and the original 2 GiB interop allocation.
The sampled stop threshold is 96 MiB including a 1 MiB receipt reserve: measured
runtime data at 95 MiB triggers stop. Data, all cache families, owned tmp and
watched system paths are included. For each unique inode it accounts
`max(logical bytes, allocated blocks × 512)`; it never assumes sparse logical
bytes are allocated storage. The aggregate interop calculation adds this runtime
footprint, which lives outside the original scratch tree. Free-space stop adds
32 MiB headroom to the 40 GiB floor.

This is a **sampled stop guard, not a filesystem quota**. The loop requests a
100 ms delay after each scan; scans, scheduling, the app's own write buffers and
termination add latency. A single sparse reservation can exceed 128 MiB before
the observer runs. The product allows a 512 MiB source file, so overshoot is a
real limitation, not an assumed worst case removed by the margin. Preflight
cannot demonstrate runtime compliance. A future breach remains a failed attempt
with state retained; the observer will not delete a library or cache to recover
headroom.

The [frozen plan](launch-plan.json) and [runtime_guard.py](runtime_guard.py) bind
the exact app/tree, paths, budget and script hash. The environment is constructed
from only fixed PATH, LANG, LC_ALL, owned TMPDIR, PYTHONNOUSERSITE and
PYTHONDONTWRITEBYTECODE values. It does not read/copy the parent environment or
set HOME. Thus parent `MUSES_GOOGLE_OAUTH_*`, other MUSES overrides, cookie paths
and developer runtime overrides are not passed by this launcher. This follows
the local macOS `open(1)` environment inheritance contract; actual launched-app
environment behavior is still untested.

Process observation uses libproc's executable path, UID and microsecond start
time, not a process name. Only the one newly observed exact main executable and
observed descendants with an unchanged hash-verified executable inside this app
can receive SIGTERM, after rechecking that identity. PID reuse or changed bytes
causes refusal. External children are observed but not signalled. A remaining
known child, changed process, external child or in-app process means shutdown
failure. A naturally closed GUI does not make the helper check pass by itself.
Short-lived or reparented descendants can escape observation, and an executable
outside this app is never assumed owned: complete process-tree absence is not
claimed even on an observer success. There is no broad yt-dlp/Deno kill and no
SIGKILL escalation.

## Results and future entry point

The [15 offline tests](evidence/tests.log) passed. Real filesystem fixtures cover
unknown new/legacy/system data, unsafe parents, ownership/mode rejection without
repair, sparse accounting, unexpected links and exact executable hash drift.
Synthetic process fixtures cover generation reuse, observed lineage, verified
stops, external-helper failure, budget failure, and retention of state on both
success and failure. These tests mock `open`, signal delivery and process
discovery; they are **not** live Launch Services or shutdown validation.
See [test receipt](evidence/test-receipt.json), [plan preflight](evidence/plan-receipt.json)
and [independent repeated preflight](evidence/preflight-receipt.json).

The plan SHA-256 is
`2453e166a266c9d74bd5b3c77d397f245b2a0ab3a24d1773b7b21d590b109b9a`;
the supervisor SHA-256 is
`8e1f7c0860b8e3068afcbfe95e179b563ef4a9d74769ef34db92d71c3603f483`.
This task ran `plan` and `preflight` through the original interop guard only.
A future operator must recheck these hashes, review this boundary, and explicitly
select `supervise --launch-isolated-app --seconds N --plan-sha256 HASH` through
that same guard with an outer timeout exceeding `N + 20` seconds. It launches the
bundle via `/usr/bin/open -n -W`, never the SwiftUI executable directly. It supplies
no URL, autoplay argument, credentials or audio command. No such launch was run.

The future namespace is single-use: existing state requires review and a new
verified plan instead of implicit resume or deletion. An interrupted operation
also requires its retained receipt/state to be reviewed. This preparation does
not prove first sound, cache budget stability, playback quality or campaign
percentiles. [cleanup-inventory.json](evidence/cleanup-inventory.json) lists only
the completed offline fixtures; root owns recoverable cleanup. The app and its
future dependencies remain retained.
