# Script input contract diagnosis

The candidate-5 host passed `NSData.bytes` directly to QuickJS without guaranteeing a trailing NUL. The pinned QuickJS 2026-06-04 API requires `input[input_len] == '\0'`. The corrected [input helper](../NativeInput.inc) copies at most 4 MiB into a `length + 1` allocation, appends NUL, evaluates using the original byte length, and frees the copy after evaluation. Both the main bundle and isolated evaluation use it. No engine, heap limit, or network behavior was changed for this correction.

The offline evidence strongly supports this defect as the explanation for the [candidate-5 locked failure](../evidence/phone-candidate-5/locked-summary.json). It does not establish the exact bytes or exception type present on the phone: that attempt retained only the generic `runtime_exception` category. A new phone run remains deferred at the user's request.

## Frozen comparison

The exact candidate-5 bundle is 1,654,732 bytes, SHA-256 `a258ea65c14b005052f88f6c12c85fef1a56764ba6fd93aee0ce8936ecb0115f`. It was not rewritten or trimmed. The old and corrected host snapshots and their hashes are recorded in [provenance](evidence/provenance.json). The unchanged QuickJS header hash is `2165f47772af9faee1798999a599fa9de850d1bf0259502dade1c25d4a588316`; its implementation hash is `a00762d2eee42316cecbc9c15efc4549b715ec500461845cd91b2a6c38190d08`.

| Exact old host experiment | Cases | Observed outcome |
| --- | ---: | --- |
| An allocated non-NUL `@` or `}` immediately after the declared bundle length | 13 | Every case returned `SyntaxError`; JS peak exactly **10,772,221 B**, matching the phone's failed bundle-load peak. No request began. |
| Explicit NUL, compile only, main/GCD/512 KiB pthread/2 MiB pthread | 28 | Every case compiled. JS peak 10,773,717 B. |
| Original `NSData`, compile only | 6 | Every case compiled in this macOS allocation run; this does not satisfy the API contract. |
| Space then NUL after the declared length | 3 | Compiled, illustrating that bytes beyond the supplied length affect the old call. |
| Actual bundle execution on a GCD worker, NUL copy/original `NSData` | 20 | Fresh runtimes executed through the first HTTP call, which an offline native substitute intercepted. |

All 70 cases matched their explicit expectation. The 13 expected JavaScript failures remain in the raw logs; they are not counted as successful bundle loads. The largest old-run native RSS was 29,884,416 B. Non-NUL failures completed in 22.4–28.3 ms on this Mac; no phone timing equivalence is claimed.

| Corrected actual host/helper verification | Checks | Observed outcome |
| --- | ---: | --- |
| Helper: nil, empty, non-NUL `@`/`}`, UTF-8, malformed source, exactly 4 MiB, above 4 MiB | 8 | Correct value or expected typed rejection; malformed JavaScript remains a syntax error. |
| Actual bundle execution, main/GCD/512 KiB pthread | 22 | Successful fresh initialization, offline HTTP substitute reached once per run, clean runtime/context/bridge teardown. |
| Main `RunProof` → `nativeEval` → isolated runtime, GCD worker | 12 | Real helper used on both inputs; valid Unicode result and teardown each time. |
| Repeated isolated runtime, deadline interruption, fresh run afterward | 14 | 12 repeated evaluations, one expected deadline stop, then successful recovery. |

All 56 corrected checks passed. Instrumentation verified the NUL at all 66 calls reaching `JS_Eval`, without altering the helper's buffer. Main-bundle JS peak remained 10,773,717 B; process RSS peaked at **30,195,712 B** (28.8 MiB). Main heap stayed 64 MiB, isolated heap stayed 8 MiB; each child had an external 10 s / 256 MiB RSS stop and bounded output. Every network entry was replaced before JavaScript execution; **zero HTTP tasks or media requests started**. A forced native `malloc` failure was not exercised; its explicit error branch was reviewed.

## Source evidence and boundaries

- QuickJS `quickjs.h:835` documents the NUL contract. `quickjs.c:37013–37021` sets the parser's end pointer, but `next_token` at `22727–22735` dereferences the next byte and recognizes end-of-input only in the NUL branch. A length argument is therefore not a substitute for termination.
- The frozen [candidate-5 host](evidence/inputs/candidate5.NativeHost.v2.m) violates this at lines 323 and 639. The frozen [corrected host](evidence/inputs/corrected.NativeHost.v2.m) uses its helper at lines 338 and 655; the helper is at lines 222–233.
- QuickJS creates its stack-top reference in `JS_NewRuntime2` (`quickjs.c:2116`); the host constructs each runtime on the worker that evaluates it. This matrix found no repeated-initialization or native-stack failure. It does not prove all possible stack depths safe.
- The diagnostic classifier reads only built-in exception types from frozen offline code and emits fixed categories; it never prints exception text, response content, cookies, or signed URLs. Production error handling remains the fixed-category implementation.
- This is input-contract and initialization evidence, not a provider availability, full transfer, background audio, or iOS lock-screen pass. There was no new network, signing, installation, or phone action.

## Commands, receipts, and retirement

The two test runners invoke `clang` once each and link the already built QuickJS/parser/transport/decoder objects. Exact commands and before/after input hashes are in the frozen run manifests; no shared dependency was rebuilt. Run from the P0 worktree using the frozen guard:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 180 -- python3 engineering/p0-2026-11-10/source-v2/ios-init-debug/run.py
python3 engineering/p0-2026-11-10/run_guarded.py --allocation source --timeout 90 -- python3 engineering/p0-2026-11-10/source-v2/ios-init-debug/run-corrected.py
```

These scripts pin their inputs and fail if another candidate is substituted. After retirement, recover the exact input copies from the dedicated Trash or reconstruct them from the frozen host snapshots and matching bundle before rerunning; do not overwrite the original receipts. Guard receipts are [old comparison](evidence/guard-old.json) and [corrected host](evidence/guard-corrected.json). Both exited 0 with no guard stop. [Summary](evidence/summary.json) indexes the individual raw logs and manifests.

The only new scratch is `/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/ios-init-debug`, hard cap 20 MiB within the existing integration allocation. [Retirement inventory](evidence/scratch-retirement.json) freezes exact files, UID, logical and allocated sizes, hashes, and final process/open-file checks. Its generated binaries, copied inputs, module cache, and test results are complete and can be moved recoverably by the root's separate frozen stage-4 plan. No cleanup was performed here; no active diagnostic process or handle is retained.
