# Stage 7 recoverable cleanup

The [frozen plan](cleanup-stage7-plan.json) moved 15 exact owned paths to
`/Users/xiaotwu/.Trash/Muses-P0-20261110-01/stage7`. The
[journal](cleanup-stage7-plan-journal.json) contains 15 completed moves, no failed
mutation and no unfinished action. All retained source/evidence hashes, source
ownership, inventories, processes and open handles were checked before the
same-volume renames, then each relocated inventory was verified.

Plan SHA-256:
`bbf9ebda8d39e5128fd6ebc5e65212baa65a51be81c312664fa7fef0fd835257`.
Execution script SHA-256:
`e66d34559080ccd611ad2ceb0b4ea1cbfcefb0055a85cd00889d91e738bdafac`.

Retired material comprises five superseded v2 builds, five copied local-run
directories, the copied public-run directory, a completed timeline diagnostic,
the completed baseline-supervisor test fixtures, and the v1 build/pointer pair.
The failed source snapshots, patches, logs and guard receipts remain in the
repository. No obsolete compiler work is kept as an evidence archive.

The retired path sums were **63,552,724 logical bytes** and **62,214,144 allocated
bytes**. Unique-inode allocated size was **62,210,048 bytes**; the 4 KiB difference
is the baseline tests' intentional hardlink pair. The sparse fixture's logical
length is separately visible and is not described as allocated storage.

The current v2 kit/build/fixtures/pointer retain **31,780,864 allocated bytes**.
All 157 v1 inputs required by the bootstrap plan had already been copied into
that kit with identical hashes; normal rebuilding uses the kit and no v1 path.
The old `--prepare` branch is provenance, not a fresh-download recipe: rebuilding
after deleting the retained kit requires recovering the v1 inputs from this
Trash or making a new verified bootstrap plan. Do not silently erase this
dependency boundary.

The unlaunched baseline app and supervisor, paused acoustic app and bounded
summaries, deferred iPhone candidate and minimum source/relink dependencies are
retained. No runtime library, preference, TCC, HTTP storage, shared SDK or
Shortcuts data was deleted. The first postcheck encountered three deliberately
named `fixture.app` test directories, so its overly broad assertion failed after
all moves had completed. That [failed postcheck](stage7-postcheck-failure-1.json)
is retained. Each directory contains only two tiny UTF-8 mock files and has no
Info.plist; exact Launch Services path checks found no registration. No move was
repeated. These fixtures are not launchable app bundles. This stage does not
claim that retained applications' registrations or foreground settings residues
have disappeared.

Actual free space was **573,210,460,160 bytes** before and **573,328,384,000 bytes**
after execution. A recoverable rename does not release data blocks, so the
concurrent free-space increase is not attributed to this cleanup: physical
recovery claimed is **zero**. No Trash was purged and no permission blocker
occurred. [Postcheck](stage7-postcheck.json) records aggregate current Trash,
active scratch, retained kits and process observations separately.
