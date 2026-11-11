# Stage 6 recoverable cleanup

The [frozen plan](cleanup-stage6-plan.json) moved 25 exact owned paths to
`/Users/xiaotwu/.Trash/Muses-P0-20261110-01/stage6`. These were the superseded
streaming build, four already-copied run directories, three superseded calibration
attempts and 17 completed calibration helper files. Current streaming binaries,
the final calibration app, physical JSON summaries, the isolated baseline and
pending iOS candidate were preserved. No raw recording exists in these materials.

The script SHA-256 is
`f7a96ee046476f2b203d2a510eb09e794d0e1647d60eb66876fa01e8a9921366`;
the plan SHA-256 is
`8a3792fd5a50426bc7a520fbff54336ed7301d52ca47a22b118931b952c2985b`.
Both preparation manifests and all their recorded evidence files were verified
before retirement. Ownership, exact inventories, processes and open handles were
checked before the same-volume renames; inventories were verified after each.
The [journal](cleanup-stage6-plan-journal.json) contains 25 completed actions and
no failed or unfinished mutation. Prior stages and failed test receipts remain.

Retired sizes were **21,837,330 logical bytes** and **22,335,488 allocated bytes**.
Actual free space was 573,607,145,472 bytes before and 573,607,079,936 afterward.
Moving files to Trash does not free their data blocks: attributable physical
recovery is **zero**, and no permanent disposal occurred. No permission blocker
occurred in these file operations. Aggregate Trash/scratch measurements and
registration observations are recorded separately in `stage6-postcheck.json`.

The current calibration app and its task-specific permission/registration state
remain a paused dependency. This stage does not reset TCC, preferences or HTTP
storage, or claim that every foreground System Settings entry has disappeared.
The physical-result report separately records that its process exited. Shared
SDKs, other apps, user library truth and Shortcuts were not changed.
