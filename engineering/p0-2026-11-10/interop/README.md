# P0 Rust / C ABI / Swift / C# / SQLite proof

Result: **the interop and persistence experiment passes on this Apple Silicon Mac**. Swift and C# load the exact same Rust dylib, make commands through its versioned C ABI, consume immutable snapshots and ordered events, and reopen the same synthetic SQLite database in separate processes. This is original MIT prototype code in the isolated P0 worktree; no production backend or personal library was changed.

## Observed checks

| Check | Result |
| --- | --- |
| Rust layout/overflow test | 1 test passed; C struct sizes 40 / 56 / 48 / 24 bytes |
| Swift seed + subsequent readback | 75 + 16 assertions passed |
| C# resume, concurrent generation race, limits, unsubscribe/release | 285 assertions passed |
| C# foreign-schema refusal, second-process owner refusal, hardlink-alias refusal | 8 + 8 + 8 assertions passed |
| Exact owned Swift process killed while resolving; C# restart | 20 assertions passed; generation 7 invalidated to 8; ordered recovery event 83 |
| Duplicate media identity | Two independent queue occurrences retained; duplicate occurrence insertion failed without changing queue or event sequence |
| Persistence and storage | 72 occurrences after cross-language restart; `integrity_check=ok`; `foreign_key_check=[]`; foreign fixture bytes unchanged |
| Immutable/lifetime contract | Snapshot remains unchanged after mutations and usable after engine release; double release and released subscriptions return invalid-handle |
| Event retention | Strict order; 64-event limit produces explicit GAP; snapshot + resubscribe recovers; previous-process event history is not silently invented |
| Same native binary | Swift `otool -L` install name and C# resolver target are the same absolute dylib path; SHA-256 unchanged through the run |

Final dylib SHA-256: `5b853b9aefe60cc4b114d8b01dd6399dd5d9923745a942d706558fafafa94325`.

The final [manifest](evidence/run-20261110-123714-dcf8d5/manifest.json) contains every exact build/run argv, duration, log hash and source hash; its [guard receipt](evidence/run-20261110-123714-dcf8d5/guard-receipt.json) records the budget/script hashes and disk observations. Rust `1.99.1`, Cargo `1.99.1`, Apple Swift `6.4.2`, .NET SDK `10.0.201`, `arm64-apple-macosx27.2`. Native linkage uses `/usr/lib/libsqlite3.dylib`; a separate read-only `sqlite3_libversion()` check returned `3.54.0`, matching the verification tool's SQLite version.

## Boundary proved

`include/muses_p0.h` is the explicit ABI. Version and struct byte counts are checked. Opaque nonzero `uint64_t` handles are kind-checked, never reused during a process, and managed inside Rust. No Rust allocation, borrowed internal object or callback is exposed to either host. Inputs are borrowed for a call; output structs are copied to caller-owned memory. FFI boundaries catch unwinding panics; invalid foreign pointers and process-wide allocation failure remain outside that guarantee.

One mutex serializes prototype commands, database access, snapshot acquisition, event polling and release. One process may own one engine. A separate OS-locked lease protects the same private database path across processes; Unix symlink/hardlink aliases are refused. The lease is separate from SQLite's own lock. This is a macOS proof, not a finalized portable lock implementation or a defence against malicious path-replacement races.

Successful commands commit SQLite state before publishing a new snapshot/event sequence. Expected-generation checks reject a superseded selection or late resolver completion. Cancellation advances the generation and invalidates the previous completion. A crashed pending resolution is invalidated durably on reopen. A ready/resolved state is not an instruction to start audible playback.

Limits: one engine, 10,000 synthetic queue entries, 64 retained events, 64 outstanding snapshots, 16 subscriptions, 4,096-byte path, 1 MiB SQLite page-cache setting, in-memory SQLite temporary storage. These are bounded experiment limits, not approved product library limits. A snapshot copies up to one queue; snapshots do not hold SQLite read transactions open.

## Gaps and P1 obligations

- C# on macOS proves .NET/C ABI interoperability only. No Windows binary/runtime, iOS device ABI, NativeAOT, sandbox entitlement, app packaging, signing or native GUI integration is proved here.
- Cancellation is logical generation cancellation. No actual network resolver, downloader, decoder or audio worker is running in this prototype; physical cancellation/acknowledgement is still required at integration.
- The database is a two-table synthetic fixture, not the generation-7 migration. [The full 21-model preservation contract](generation7-contract.md) and [227-property mapping](generation7-field-map.md) define the work still required. Numeric fixture IDs do not replace production UUIDs or source/account identities.
- This synchronous mutex/SQLite implementation must not run on the UI thread or a real-time audio callback. The production actor/worker topology, bounded command admission, timeout/backpressure, query paging and snapshot publication costs still require implementation and measurement.
- Event history is a bounded in-memory stream. Sequence numbers persist, but clients must resnapshot after gaps/restarts. Durable remote-write journals are separate user evidence and must not be built on this transient event ring.
- Strict version/size matching is enough for P0; production needs a documented ABI evolution/feature-negotiation policy, safe Swift/.NET ownership wrappers, structured sanitized errors, schema upgrades, and corruption/disk-full/power-loss fixtures. FFI pointer validity remains the caller's responsibility.
- No migration, remote account write, actual music playback or UI/UX claim is made by these checks.

## Reproduction and retained evidence

Run only through the frozen disk guard:

```sh
python3 /Users/xiaotwu/Code/Project-Muses-P0/engineering/p0-2026-11-10/run_guarded.py --allocation interop -- python3 /Users/xiaotwu/Code/Project-Muses-P0/engineering/p0-2026-11-10/interop/build_and_verify.py
```

`build_and_verify.py` creates one unique run directory under the allocated scratch root. Cargo target/home, Swift/Clang module caches, temporary files, .NET CLI home, NuGet caches and MSBuild outputs all stay under that directory. Cargo runs offline and NuGet package sources are cleared; no third-party source/package download is required. `.NET` development-certificate generation and tool-path bootstrap are explicitly disabled in the final runner.

All four attempts remain represented by bounded manifests/logs/guard receipts:

1. `123234-0d2931`: Swift test helper's unlabeled default parameter caused a compiler error; fixed with an explicit overload.
2. `123309-4ef255`: initial full proof passed; superseded by the extra foreign-schema/alias checks and exact shared install-name target.
3. `123529-390a85`: putting the OS lease directly on the database file caused the native open to fail with storage status 5 on this host; no personal database was involved. The final implementation uses a separate lease and refuses aliases. This failed attempt is preserved, not relabeled as passing.
4. `123714-dcf8d5`: final build and all checks passed, with zero Swift/Rust errors and .NET reporting zero compiler warnings/errors. .NET printed a nonfatal workload-verification notice; no workload install/update was attempted.

The first successful .NET bootstrap printed a development-certificate installation message. The coordinator's subsequent read-only native check found one public `localhost` certificate, valid from **2026-04-06** to **2027-04-06**, predating this task; no newly created localhost certificate was found in the current search list. The message alone does not establish a new certificate. No Keychain deletion or modification was performed by the audit. The final runner suppresses that bootstrap action.

Scratch was measured at **153,313,280 allocated bytes** across the four run directories, below the 2 GiB allocation; all build/test sessions have exited. A read-only process/open-file inventory found no remaining interop process or open file (apart from the inventory commands themselves). [The exact path inventory](evidence/scratch-inventory.json) marks all four compiler/cache/fixture directories obsolete after evidence capture. No cleanup has been executed by this agent: the coordinator will freeze the combined cleanup manifest and use recoverable Trash. Space recovered by this agent: **0 bytes**. No obsolete compiler cache needs retention as evidence.

The implementation follows the documented [Rust C layout rules](https://doc.rust-lang.org/reference/type-layout.html#the-c-representation), [.NET native library loading](https://learn.microsoft.com/en-us/dotnet/standard/native-interop/native-library-loading) and [calling conventions](https://learn.microsoft.com/en-us/dotnet/standard/native-interop/calling-conventions), and [SQLite connection/serialized-mode semantics](https://www.sqlite.org/c3ref/open.html). These primary references were consulted through Context7; runtime results above come from the actual local checks.
