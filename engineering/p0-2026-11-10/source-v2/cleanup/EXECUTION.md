# Stage 3 execution result

The frozen [plan](cleanup-stage3-plan.json) and script were verified and executed
through the original disk guard. All 14 exact paths moved successfully to the
dedicated Stage 3 Trash; no failure or permission blocker was recorded. The
immutable preparation plan still says `stage3_has_been_executed: false` because
it records pre-execution state; the [journal](cleanup-stage3-plan-journal.json)
is the execution authority. Its successful actions were read back.

The move set contained 42,522,806 logical bytes and 45,973,504 allocated bytes.
The complete task Trash now contains 2,119,118,848 allocated bytes after unique
inode accounting. Its per-path sum is 2,119,135,232 bytes: the existing 16 KiB
SQLite hardlink pair from Stage 1 explains that difference.

Actual filesystem free space changed from 574,371,094,528 to 574,369,918,976
bytes during the observed window. Other active work also ran in that interval;
this delta is not attributed to cleanup. Same-volume renames did not free data
blocks, and the physical-recovery claim is **zero**. No permanent deletion was
performed. See the [measured result](stage3-result.json).

The current parser, desktop decoder inputs, integration build and phone
candidate, live media and original unfinished phone dependencies remain active
for source/physical-device validation. No user library, credential, shared SDK,
system-managed cache or installed production application was touched.

Guard receipt: `7ab3e13a64ae4656a2d69467ff504acd`.


## Stage 4 — source checkpoint and deferred phone run

The seven exact paths in `cleanup-stage4-plan.json` were verified with `retire_stage4.py` and moved recoverably after a clean preflight. Plan SHA `9d81691501a4a32a76ba77888b58d4152073836f0d8a6e62ac4cddb69ed94a93`; script SHA `8b3954bbdff64d69fbb054bb9b9e7b8792cf3c45e60951f6f1e76ccee6d22312`. The completed journal has no unfinished or failed move. A wrong required-manifest path stopped preparation before any move; that record is retained in `stage4-preparation-failure.json`.

The move retired old calibration builds, candidate 5, finished initialization helpers, two duplicate AAC files and a failed partial: 65,256,888 logical bytes and 67,006,464 allocated bytes at execution. Current candidate 6, active source dependencies and three distinct media remain for unfinished phone/macOS work. No phone or system registration was changed by these filesystem moves.

`stage4-result.json` records the independently measured total Trash (2,173,034,496 unique-inode allocated bytes), active scratch (134,905,856 allocated bytes) and actual free space. Free space changed from 574,332,813,312 to 574,332,731,392 bytes; this is not attributed to file removal. No Trash was purged, physical recovery claimed is zero, and no permission blocker occurred. Earlier frozen observations remain historical measurements rather than an assumed additive current allocation.
