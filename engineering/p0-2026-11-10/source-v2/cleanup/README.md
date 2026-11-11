# Stage 3 cleanup plan — prepared, not executed

The [frozen plan](cleanup-stage3-plan.json) contains 14 completed, task-owned scratch directories. Every entry was checked against its owner evidence, UID 501, recursive file hashes/metadata, `lsof -nP +D`, and a process-command scan. No active handles or matching processes were observed. The script's read-only preflight passed with `executed=false`, `journal_written=false`. The Stage 3 Trash directory and cleanup journal do not exist at preparation completion.

The exact [inventory](stage3-inventory.json) totals 42,522,806 logical file bytes and 45,973,504 allocated bytes. Unique-inode accounting equals the per-path sum for this set; no hardlink allocation difference was found. Actual free space at inventory time was 574,385,537,024 bytes. This plan only relocates files on the same volume. Physical bytes recovered are **zero**, and no free-space recovery is promised.

| Proposed group | Paths | Logical bytes | Allocated bytes |
|---|---:|---:|---:|
| QuickJS-NG comparison | 1 | 12,814,652 | 14,508,032 |
| Control and generated-host tests | 1 | 6,234,494 | 6,266,880 |
| iOS policy and real-file muted ABI helpers | 4 | 6,863,455 | 6,950,912 |
| Old local, AVIO, decoder and long-test helpers | 7 | 8,656,604 | 8,761,344 |
| Previously retired unused dependency headers | 1 | 7,953,601 | 9,486,336 |

Destinations are flat, unique names beneath `/Users/xiaotwu/.Trash/Muses-P0-20261110-01/stage3/`. The existing Trash contents, root cleanup scripts, plans and journals are unchanged. Old successful/failed test receipts and logs were also preserved as 35 small files totaling 19,522 bytes under [retained-test-evidence](retained-test-evidence/); the original owner evidence remains intact.

Explicitly preserved: `v2-parser`; `v2-transport/decoder-inputs`; macOS/iOS dependency objects; `long-fixtures`; current `v2-integration/build` and `iphoneos`; all live source media; original source/audio phone material; old recovery plans, failed receipts, and journals. The generic `.bin`/`.partial` files in the old local transport tests are deterministic byte fixtures, not retained live media. No candidate in this exact plan contains an audio/video media extension. `long-fixtures` is deliberately outside this move set; root may assess it separately without silently expanding this plan.

The root [retire_scratch.py](../../retire_scratch.py) is frozen at `2b8f6f7a675908bbd7e002199fcb8cefb69acfe6446289fc52c85fba87bb8bd8`. It hardcodes the original Trash root and rejects nested destinations. The separate [Stage 3 adapter](retire_stage3.py) retains the journal/resume model, targets only the new Stage 3 directory, and adds frozen content/metadata inventories, all-path preflight, process checks and post-rename verification. It defaults to read-only preflight. An interrupted execution may resume only with the same plan/script hashes and exact pending inventory; successful moves are never repeated. Failures remain in the journal. No purge operation exists.

[Frozen hashes](frozen-hashes.json):

- Plan: `497031deacfa2fd8b0ef649a8c5974281b06a3720c8c960a2cd561c3e8735b67`
- Stage 3 script: `edcaea66f8a1cf5b8612c1aa658f3740959cf356c177b3a87c278bada40f32d4`
- Inventory: `8ec4ad8373666378a187edb8221e1726217381622e44ea41ec5867b9cb770fe6`

Preparation guard receipt: `bcb06ce64ba340488abe4499b54cfb2e`. Read-only preflight guard receipt: `f939c187376d4dbd8280d4973c267b3e`. No build, source-network request or device action occurred during this cleanup preparation.

After root reviews the exact plan, this command performs the recoverable moves. It has **not** been run:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 180 -- python3 engineering/p0-2026-11-10/source-v2/cleanup/retire_stage3.py --plan engineering/p0-2026-11-10/source-v2/cleanup/cleanup-stage3-plan.json --plan-sha256 497031deacfa2fd8b0ef649a8c5974281b06a3720c8c960a2cd561c3e8735b67 --script-sha256 edcaea66f8a1cf5b8612c1aa658f3740959cf356c177b3a87c278bada40f32d4 --execute
```

Omit `--execute` to repeat read-only preflight. Any changed inventory, evidence hash, unexpected destination, active process or inconclusive handle check stops the adapter. After a real execution, report the journal's actual free-space observations, retained Trash and zero physical-recovery claim; do not substitute the planned allocated-byte total for reclaimed disk space.
