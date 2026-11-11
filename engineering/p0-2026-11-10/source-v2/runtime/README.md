# Offline runtime safety comparison

Keep the pinned QuickJS 2026-06-04 engine for the current P0 integration. QuickJS-NG 0.18.0 is a tested embedding candidate, not an adopted dependency. The corrected baseline no longer reproduces the earlier SIGSEGV, and both engines need the native reduced input to stay within the 64 MiB extraction budget. No production files, media requests, phone state, or runtime limits changed in this comparison.

The [embedding probe](embedding.c), [build script](build.py), [bounded runner](run_tests.py), and [budget](runtime-budget.json) use the same public player input, corrected extraction bundle, and full-source JSC reference solver as the parser proof. Native code embeds the engine directly; no JavaScript CLI runtime is required by the resulting probe. Build tools are development dependencies only.

| Check | Pinned QuickJS 2026-06-04 | QuickJS-NG 0.18.0 |
|---|---|---|
| Corrected full AST, 64 MiB | Clean exit 1 near the limit; error category unavailable; no SIGSEGV | Allocator denial, returned exception with a null error value; clean teardown and fresh 8 MiB instance succeeds |
| Reduced input, 64 MiB; solver, 8 MiB | Pass; solver exactly matches the JSC reference | Pass; solver exactly matches the same reference |
| Reduced extraction peak | 30,919,314 B custom allocation accounting; 40,288,256 B native max RSS | 33,259,874 B backing allocations; 28,831,099 B logical usage at the post-extraction mark; 42,844,160 B native max RSS |
| Synthetic allocation failure | Not repeated in this comparison | Seven retained 1 MiB arrays, then an uncatchable engine-limit exception; zero live backing allocations and fresh instance succeeds |
| Host cancellation | Not repeated in this comparison | Atomic flag set by another thread after 30 ms; JS try/catch cannot swallow the interruption; completion in 35 ms, zero live allocations, fresh instance succeeds |
| Context creation failure | Not repeated in this comparison | A deliberate 1-byte logical-limit fault returns null; zero live allocations, fresh instance succeeds |
| Existing JS fetch/stream shim | Not repeated in this comparison | JSON POST, Response clone/body, pending-request abort and ReadableStream pass in 14 jobs using deterministic native mocks; zero network requests and zero live allocations |
| iOS | Existing P0 evidence remains separate | Engine and embedding probe compile to arm64 iOS 17 deployment objects using iPhoneOS 27.2 SDK; no link, install, or device-runtime claim |

The final NG native maximum RSS was 82,231,296 B during the full-input failure, below the unchanged 256 MiB process threshold. A 20 ms external sampler enforces the running-process threshold; native `getrusage` values also cover peaks missed by sampling and are checked in the frozen evidence. The 64/8 MiB limits are applied both to NG logical memory and the probe's backing allocator, including its headers. Those counters differ because NG owns an internal arena; they must not be reported as interchangeable. NG releases the extraction runtime before creating the solver runtime. The baseline harness keeps its extraction runtime alive during its solver check, so the RSS figures are observations of these harnesses, not a controlled performance ranking.

The corrected extraction bundle includes the same scoped JSON `structuredClone` used by the frozen P0 host, which Meriyah needs for plain AST records; upstream diagnostic logging is disabled. The earlier incomplete bundle and its SIGSEGV receipt are preserved and labeled historical. It does not establish a current engine defect. The corrected original-engine full parse peaked at 67,105,131 of 67,108,864 allocation bytes and returned a failure whose error category the baseline harness could not recover; this is consistent with exhaustion but is not a positive error-message classification.

NG's first probe run contained two overly strong assertions: every exhausted-heap exception must contain an uncatchable Error object, and every memory rejection must reach the backing allocator. Actual results disproved both assumptions. The final test accepts a returned exception plus recorded allocator denial as bounded allocator failure without claiming uncatchability. The fixed typed-array workload separately verifies an uncatchable logical-limit exception after seven completed allocations. [Failed assertion records](failed-assertions-01.json), initial receipts, and the [rejected callback compile](failed-build-01.json) remain intact. All six final NG checks pass; the full-AST check is a graceful-failure check, not successful extraction.

Integration changes would be required before any future adoption:

- `JSMallocFunctions` adds `calloc`; callbacks receive `void *opaque`, not public `JSMallocState *`. Maintain independent live/peak/denial counters; do not cast the old callbacks. NG's zero memory limit means unlimited, so every runtime must receive its explicit nonzero limit.
- `JSInterruptHandler` receives `JSContext *`, not `JSRuntime *`. The first compile caught this mismatch. Preserve cancellation/deadline state lifetime until runtime teardown and join any test cancellation thread first.
- `JS_IsError` takes only the value; `JS_IsUncatchableError` is available. NG makes `InternalError` uncatchable. Existing native host calls that use `JS_ThrowInternalError` for ordinary recoverable bridge failures need a deliberate error-type decision; a mechanical swap changes JS catch behavior.
- Check both runtime and context creation for null. During exhausted-heap failure, avoid allocating error strings, properties or backtraces. Retrieve/free the exception, report host-owned numeric status, free values/context/runtime, and start a fresh instance. A missing Error object must not be treated as successful evaluation.
- Pending-job, value, buffer and runtime/context APIs used by this offline harness otherwise compile as shown. The actual Objective-C network bridge, Unicode text encoding, timers, URL parsing, streaming media, background cancellation and iOS linking/runtime were not exercised here.

Source provenance is fixed by the [bootstrap](bootstrap.py) and [final manifest](manifest.json). The official v0.18.0 amalgam archive is 571,908 bytes, SHA-256 `6c05066a6b62b483e2ba0f83d7a16688c6958182b214bfd693529434cef84a9e`, from the [official release asset](https://github.com/quickjs-ng/quickjs/releases/download/v0.18.0/quickjs-amalgam.zip). The retained source is unchanged. `quickjs.h` documents the allocator at lines 472–478, interrupt callback at 1191–1193, and error predicates near 843. The amalgam's logical-limit checks are near 12901–12972 and InternalError/OOM handling near 19386–19481. Exact extracted hashes and build commands are retained in `evidence/`.

[Third-party notices](THIRD_PARTY_NOTICES.txt) preserve the MIT notices from the downloaded source and the Unicode License V3 notice embedded in its Unicode tables. They also include the MIT Web Streams polyfill notice used by the offline shim. The no-GPL boundary is unchanged.

Run only through the existing parent guard, with `source` allocation:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 60 -- python3 engineering/p0-2026-11-10/source-v2/runtime/bootstrap.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 60 -- python3 engineering/p0-2026-11-10/source-v2/runtime/run_tests.py baseline
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 180 -- python3 engineering/p0-2026-11-10/source-v2/runtime/build.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 180 -- python3 engineering/p0-2026-11-10/source-v2/runtime/run_tests.py ng
```

The bootstrap receipt freezes its original copied inputs, including the historical incomplete bundle. It refuses replacement if the upstream parser scratch changes; use the already frozen inputs and recorded corrected-bundle copy for this attempt instead of rerunning bootstrap over newer parser output. Runtime scratch is capped at 50 MiB within the existing integration allocation. Core dumps are disabled for all probe processes. [Cleanup candidates](cleanup-candidates.json) inventory the exact owned scratch subtree after all processes exited; no deletion was performed. Parent coordination will move obsolete artifacts to dedicated Trash after freezing the combined cleanup plan. Immutable attempt manifests in `evidence/` intentionally describe earlier source/binary revisions; `manifest.json` describes this final checkpoint.
