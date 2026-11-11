# Muses P0 — isolated implementation and feasibility record

Status: **in progress; the P0 exit gate has not passed**. User authorization to execute the full P0–P9 plan was received on 2026-11-10. This directory contains working prototypes, contracts and bounded evidence. It is not a new Muses release or the production Core repository.

Tracking: [XW-135](https://linear.app/xiaotwu/issue/XW-135/muses-完整重构-p0功能契约与跨平台核心验证), [approved complete plan](https://linear.app/xiaotwu/document/muses-完整后端重构总方案已确认执行-34f298f3ff59).

## Scope and ownership

Worktree `/Users/xiaotwu/Code/Project-Muses-P0`, branch `codex/p0-complete-backend-validation`, family base `d4afe230ba20f4697829309225b7361e43745da3`. The production family and platform working trees were not modified by these prototypes. Engineering material stays outside the public `docs/` website. Temporary proof executables are not platform release builds; signing, notarization and publishing of real products remain in their owning platform repositories.

The approved outcome is a complete replacement backend with native platform UI, MIT application logic, macOS first, and later Windows/iOS. Explicit downloads require a capable allowed source; local import/scanning stays out. Video belongs inside the main content area. The broader scope remains [F01–F22 / P0–P9](contracts/scope-and-acceptance.md).

## Evidence map

| Slice | Implemented and observed | Important limit |
| --- | --- | --- |
| [Core ABI / persistence](interop/README.md) | One Rust dylib used by Swift and C# on macOS; 1 Rust test, 91 Swift and 329 C# assertions; transactional synthetic SQLite state, crash recovery, occurrence identity, immutable snapshots, lifecycle/error and bounded-event behavior | C# on macOS is not Windows runtime proof. Logical cancellation is not cancellation of actual network/decoder work. Two-table proof is not full migration. |
| [Generation-7 preservation](interop/generation7-contract.md) | 21 models / 227 stored declarations mapped with source hashes; queue/bookmark/progress unit distinctions identified | No personal database was read or migrated; fixture migration and business reconciliation still need implementation. |
| [Native audio](audio/README.md) | Fresh minimal LGPL FFmpeg + miniaudio, AAC/Opus, local/controlled HTTP decoding and seek, bounded 512 KiB PCM pool, late next preparation, one output clock, cancellation and native callback tests | Component runs were silent. Real routing, interruption recovery, actual provider streaming, full DSP/AutoMix and long-run product acceptance are not established. |
| [Source runtime](source/README.md) | Restricted QuickJS host with real URLSession network, catalog/search/continuation, capability/heap/deadline/cancellation probes; JSC and native Swift alternatives investigated separately | Catalog and first media bytes do not prove complete media transport. Failed extraction/transport/resource experiments remain in evidence. |
| [Bounded source continuation](source-v2/README.md) | Native syntax windows, the unchanged 64 MiB QuickJS extractor, 8 MiB isolated solver and 256 KiB native transport; complete AAC/Opus and a fresh second recording, full decode and 30-second seek comparisons; about 85.3 MB maximum observed desktop RSS | Tested public profiles/samples only. Actual locked first audio passed, but candidate 5 failed initializing the second source; candidate 6 repairs a script-input contract and needs physical verification. No production App integration. |
| [macOS continuation](macos-p0/README.md) | Isolated 0.6.3 baseline prepared, real FFmpeg replacement/relink proof, draft corpus/campaign tools, muted public AAC streaming before full transfer, and bounded acoustic calibration results | Baseline not yet measured; physical marker detection failed despite later reported beeps. EOF/drain, public Opus streaming and deployment-target consistency are being completed separately. Formal app integration and actual first-sound statistics remain open. |
| [Embedded video](contracts/embedded-video-interaction.md) | Native style preservation, placement/controls, one sound owner, timeline mapping, navigation/fullscreen/focus and failure semantics; reviewed and corrected | Contract only; production UI has not been changed/rendered and runtime video acceptance is pending. |
| [Reference app](contracts/reference-observations.md) | Official BitChord 1.9.1 in an isolated AVD; anonymous search, playback state/queue, manual Next/seek/pause, embedded video return, source and download entry observations | Silent AVD; no inferred audibility, reliability, authenticated sync, download completion or protocol equivalence. |
| [Measurement protocol](contracts/validation-protocol.md) | Real-output onset, failure accounting, corpus freeze, cold/warm/account/network dimensions and physical-device evidence rules | The ≥30 playable-item corpus and ≥100 per-build comparison have not been frozen/run; Mac 0.6.3 baseline is unmeasured. |

Physical-phone attempts and their final interpretation are recorded separately in [iOS calibration](evidence/ios-calibration.md). Synthetic calibration validates only the stated native-output/catalog dimensions; it cannot close the actual source-media gate.

The subsequent [candidate 5 locked trace](source-v2/evidence/phone-candidate-5/locked-summary.json)
uses actual main-thread application/scene/protected-data state and complete real
media. It confirms the first source while locked; at +30 seconds a fresh second
source failed during script initialization, before HTTP, then stopped with
`source_failure`. This is not a successful transition or the intended 90-second
watchdog stop. The NUL-termination repair and candidate 6 are documented in the
continuation without changing those failed receipts.

## Architecture decisions

1. Retain the approved native UI + Rust Core + SQLite direction. The ABI/persistence primitive is feasible in the tested environment; production actors, host bindings and full migration belong to P1 after the remaining P0 gates.
2. Keep a source adapter boundary. Do not couple queue or playback identity to the current extraction library or an expiring signed URL. Capability, recording identity, availability time, authorization scope, transport, expiration and actual format are separate fields.
3. Keep QuickJS's **64 MiB JavaScript heap**. Process RSS is a different measurement and includes the host, network and other allocations. Whole-player AST parsing did not fit the tested 64/128 MiB heaps. The source-v2 continuation instead uses bounded native syntax windows and passes only required declarations to the pinned extractor; its live full-media results support this adapter direction without expanding the JS budget.
4. JSC on macOS completed player extraction around 226–229 MiB process RSS, but it is not a replacement with the same enforceable heap limit. The IOS media client failed continued transfer after an initial chunk; the tested WEB response offered SABR descriptions without direct URLs/ciphers. Neither is a successful full-source player.
5. A native MIT Swift alternative was evaluated as a separate adapter candidate. Its first external **256 MiB RSS** guard failed. One explicit diagnostic exception used a **512 MiB RSS ceiling / 60 seconds / ≤16 MiB declared media length**, keeping the existing scratch/free-space budgets. It returned 34 streams in about 5.1–5.4 seconds, but exceeded the diagnostic ceiling at 541,786,112 observed RSS bytes before a first media chunk completed. This failed experiment does not approve a 512 MiB production runtime, prove iOS background feasibility, or relax the 64 MiB catalog budget. Source-v2’s bounded native parsing and transfer supersede that experiment as the current candidate; see [XW-145](https://linear.app/xiaotwu/issue/XW-145/p0-来源门槛完整媒体传输与解析内存方案).
6. FFmpeg/miniaudio are feasible primitives for tested native audio. The proof uses static LGPL archives. Production version/security review, corresponding source/build materials and a verified relink/replace pathway must be settled before distribution. The GPL-enabled Homebrew executable only generated owned sine fixtures; its libraries are not the selected runtime.
7. Do not bulk-rebind production UI or start P1 cutover while the source, physical lifecycle/resource and baseline gates remain unresolved. Change the failed adapter decision, keeping the complete feature scope and acceptance targets.

## Guidance that the approved rewrite supersedes

The new Core contract supersedes the old architecture's single-provider Track identity, mandated old playback/database implementation and iOS Public foreground-only product direction for this rewrite. It does not loosen native visual preservation, credential/account authorization, user-data protection, platform-specific release channels, or disk hygiene. Existing platform guidance will be changed explicitly in each owning repository when implementation enters it; no old production constraint is silently edited here.

Old Linear acceptance issues keep their identifiers, relationships and evidence. Old Done statuses do not prove a new implementation; unfinished historical acceptance is not silently closed. P1–P9 are XW-136–XW-144 in the Muses project, linked by dependencies and still Backlog.

## Resource and cleanup record

The following two-stage account is the first checkpoint, not the current scratch
inventory. The subsequent source continuation records its own [cleanup execution](source-v2/cleanup/EXECUTION.md)
and retained candidates. Candidate 5 replaced the old calibration app; candidate
6 is the current compiled repair awaiting physical verification. The original
cleanup plans and journals remain immutable.

Task scratch: `/Users/xiaotwu/.muses/tmp/p0-20261110-01`, total allocation **8 GiB**, free-space floor **40 GiB**. Initial measured free space was **573,794,725,888 bytes**. `run_guarded.py` monitors allocated blocks and process deadlines, preserving both successful and failed receipts. Its frozen SHA-256 is `3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0`; initial budget SHA-256 is `7b27e21065887ba0a9072552afa31f64c307f1df6ff8eb4c3ebac25799fe3cbc`.

The first completed-stage cleanup uses [frozen plan](evidence/cleanup-stage1-plan.json), `cleanup_stage1.py`, and [journal](evidence/cleanup-stage1-journal.json). It moved six owned paths, **1,751,207,936 allocated bytes**, into `/Users/xiaotwu/.Trash/Muses-P0-20261110-01`. This includes the obsolete interop builds, reference AVD/APK/project and exact AVD registration. It stopped the dedicated emulator/server; subsequent checks found the emulator/crash helper, task IDE/worker and observed adb processes exited, and the task gRPC discovery registration gone.

The second cleanup uses a [frozen plan](evidence/cleanup-stage2-plan.json), `retire_scratch.py`, and [journal](evidence/cleanup-stage2-plan-journal.json). It moved 49 obsolete source/audio build, cache, partial-media and private diagnostic paths, **322,048,000 allocated bytes**. A preparation check stopped when three preliminary audio logs lacked exact retained copies; those bounded logs and the [failed preparation record](evidence/cleanup-stage2-preparation.json) were preserved before any scratch move. All 115 successful/failed guard receipts were retained. Each move checked ownership and open handles; the journal has no unfinished move or cleanup failure.

The final [measured cleanup summary](evidence/cleanup-summary.json) records **2,073,239,552 allocated bytes** in the dedicated Trash (unique-inode accounting; the intentional 16 KiB SQLite hardlink fixture is counted once) and **32,067,584 allocated bytes** retained in active task scratch. The retained set is the minimum unfinished iOS probe, native iOS objects, small pinned source/fixtures and bounded evidence. Candidate 4's corrected lifecycle collector is compiled but not signed/installed; the tested candidate 3 remains on the phone, with its audio stopped by the watchdog. [XW-146](https://linear.app/xiaotwu/issue/XW-146/p0-真机门槛核对锁屏状态与后台下一首证据) tracks the remaining device evidence.

These are recoverable relocations, **not physical space reclaimed**. Stage 2 observed free space change from 574,721,187,840 to 574,720,835,584 bytes amid other system activity; the final measurement was 574,718,361,600 bytes free. Attributable physical recovery claimed is **0 bytes** and no Trash was purged. No permission blocker was encountered. Shared SDKs, other AVDs, OS-managed caches and existing projects remain. The task IDE recent-project entry and the dismissed onboarding preference are explicitly recorded residues, not claimed removed.
