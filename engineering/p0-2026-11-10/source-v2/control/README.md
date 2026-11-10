# Native operation control

[NativeControl.inc](../NativeControl.inc) provides one shared operation boundary for the P0 metadata host, native player parser, isolated JavaScript solver and native media transfer. It keeps the pinned QuickJS engine. It has no URL, credential, JavaScript, bridge, or user-interface access.

`P0V2BeginOperation(seconds)` accepts a finite positive deadline of at most 180 seconds and rejects BUSY without changing the current operation. Begin, End, Bind, Unbind and ShouldStop belong to the same serial source worker. `P0V2Cancel()` may run on UI or monitor threads. A generation and owner-thread token reject stale or foreign worker operations. The first stop reason wins and uses fixed strings: `none`, `cancelled`, `deadline`, `rss_limit`, `rss_observer_unavailable`, `watchdog_unavailable`, or `transfer_binding`.

A native pthread checks monotonic time and Mach resident memory every 100 ms. It cancels a bound transport on an observed deadline or RSS breach even while the source worker is blocked in a network read. The 256 MiB RSS boundary is an observation/cancellation limit, not a hard allocator cap. JavaScript still has its separate 64 MiB outer and 8 MiB solver limits. Failed RSS observation stops the operation. Peak RSS and reason remain readable after End; a successful new Begin resets them.

The binding mutex remains locked during `mt_cancel`, so Unbind cannot return while the module is using that handle. The owner must finish/join transport work, Unbind, and only then destroy the handle. End defensively cancels a still-bound handle but never destroys caller-owned media state. End marks the operation as ending and joins its watchdog before accepting another Begin. `V2ShouldStop()` never enters the transport or takes its binding mutex; it updates atomic state and wakes the watchdog, avoiding callback lock inversion. A foreign thread's ShouldStop fails closed. Child worker callbacks need an explicit owner design rather than sharing the API implicitly.

Integration requires Begin/End around the whole metadata-plus-transfer operation, and a single End path after cleanup. Both QuickJS interrupt callbacks, outer host loop, each event/timer batch step, and pending-job drain check ShouldStop. The generated host limits the drain to 128 jobs per tick and native timers to 128. The parser's trusted cancellation callback calls ShouldStop. Native transfers bind immediately before I/O and unbind on every exit before destruction; availability waiting uses short polling sleeps. Runtime/context allocation failures are checked before any use. Error handling retrieves/frees an exception and reports fixed native categories without property/string/stack evaluation in the exhausted runtime. `P0V2RunSource` uses a shorter shared 45-second limit; the independent iOS audio observation lasts 90 seconds from audio start.

Local results:

| Check | Result |
|---|---|
| Deterministic module checks | 122 passed: timeout validation, BUSY, foreign/stale owner, cancellation versus Unbind lifetime, new-operation reset, deadline/RSS/RSS-observer failure, duplicate/late binding and 20 repeated Begin/End cycles |
| Production clock/RSS implementation | A blocked-worker smoke using real monotonic time and Mach RSS observes deadline cancellation; new operation succeeds; no network |
| iOS compilation | arm64 object with iOS 17 deployment target and iPhoneOS 27.2 SDK; no device execution claim |
| Exact generated-host wiring | 42 checks passed, with a fresh successful operation after every case |
| Self-replenishing Promise chain | 150 ms shared deadline; exited in 152.54 ms |
| Native timers | Exactly 128 accepted; timer 129 rejected |
| Isolated solver infinite loop | Shared deadline exited in 150.14 ms; separate external cancellation exited in 31.39 ms, before its local 1-second cap |
| Frozen public player through `V2FilterEvent` | Pre-cancel and cancellation during parsing both return `cancelled`, zero output and zero live native parser allocations; 0.07 ms and 1.35 ms respectively |
| Generated-host resource envelope | 22,757,376 B native maximum RSS; external 10-second/256 MiB guard; zero metadata requests |

The [host-wiring driver](host-wiring/driver.m) includes the actual generated host after renaming its CLI main, and links its existing native objects. It does not recreate the host loop. Input host SHA-256 is `1f10d3e9fc4591615005e718bce1ec90850c704eb4bf0bfa7188d51c995b3bb8`; root desktop binary `3d8365b3c4f099e4ff5d116e7fb343e3aa325a5dfae99271bdc8abbeb5d6ec5e`. The generated host and all linked objects/source dependencies are hashed before and after compilation. Its fixture logs intentionally contain expected failure records; the final driver summary defines the check outcome. These tests use no media network and do not establish iOS background behavior.

The implementation remains SHA-256 `0876bc263d605cd68eb0c8b9b308da39dfc90d437784517722a70f325604091e`. [Evidence](evidence/) contains exact build commands, source/binary hashes, raw bounded logs and parent guard receipts. [Final manifest](manifest.json) hashes this checkpoint. [Cleanup candidates](cleanup-candidates.json) list the owned scratch and its measured allocated/logical sizes; no deletion was performed. Parent coordination owns recoverable cleanup. The 10 MiB control scratch cap is inside the existing integration allocation, with a 40 GiB free-space floor.

Run only through the frozen parent guard:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 90 -- python3 engineering/p0-2026-11-10/source-v2/control/run.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 90 -- python3 engineering/p0-2026-11-10/source-v2/control/host-wiring/run.py
```

Read-only integration review found and root corrected the unguarded pending-job loop, missing batch checks, native timer count, error-property inspection and missing `RunPolicy.h` build provenance. No concrete lock inversion was found in the reviewed Control/transport/callback paths. New iOS source separates source/audio/monitor/evidence queues and binds callbacks to a run; signing, installation, audible output, sustained lock and real source delivery remain separate acceptance gates.
