# P0 bounded cold player extraction

The current public player can now be reduced and extracted within the unchanged **64 MiB QuickJS main heap / 8 MiB isolated evaluator** limits. This is a parser proof, not a complete media-transfer or lockscreen-playback pass. Original `source/` evidence is unchanged.

## Results

Cold input is a public, unauthenticated `player_es6` script obtained from `iframe_api`, with no saved cookies or warm extraction cache. It is retained only in task scratch:

`/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser/fixtures/player.js`

Input: **2,658,728 bytes**, SHA-256 `5f2035b38e20c1e57ad8e51ada9ea82d1eaac59f2a4603ebd851f421e3a3f5dd`.

| Stage | Result | Memory / timing |
| --- | --- | --- |
| Native cold preprocessing | 189,450-byte reduced IIFE, 1 solver match, 2 timestamp matches | 7,401,998-byte tracked peak; zero tracked allocations retained; about 1.95 s; 14.3 MB process peak |
| Unchanged YouTube.js analyzer/extractor on reduced source | 179,564-byte solver; signature timestamp 20760 | 30,919,314-byte QuickJS peak under 64 MiB; about 0.63 s |
| Isolated solver, synthetic n/signature inputs | Both returned nonempty transformed strings | 2,300,509-byte QuickJS peak under 8 MiB / 1 s |
| Full-source reference extraction on diagnostic JSC | **Byte-for-byte identical solver** | 194,871,296-byte process peak; about 1.43 s |
| Native lifecycle/window checks | 139 checks passed | Repeated cap and malformed-input recovery, allocator restoration, concurrent-call rejection, long lexical window, cancellation and deadlines |

Reduced-source SHA-256: `be8ae511cec64bb48b61ccb280f30151ef5bb61dec2466457eb471b2a5b171a9`.

Both extracted solvers have SHA-256 **`0864285e763dfe18696fd8592925db8942108e383919388a11db4715658dc198`**. Thus preprocessing preserves the pinned upstream extraction result for these exact current player bytes. The JSC run is a comparison reference, not the proposed runtime or a new memory allowance. Its external 256 MiB RSS sampling is not an in-process heap limit.

## Why the previous peak occurred

YouTube.js 18.3.0 `JsAnalyzer` first constructs a complete Meriyah AST with ranges, then retains that AST, the original source, declaration metadata, dependency/dependent Maps and Sets together. `JsExtractor` still needs the analyzer during emission. Calling GC after emission cannot remove the cold AST peak. The new offline JSC reference reaches about 195 MB without any network response or media buffer, isolating a substantial parser cost from transport lifetimes. QuickJS's live allocation decreases from about 30.7 MB to 5.2 MB after releasing the reduced analyzer, proving that its AST is no longer retained through the isolated solver stage.

The pinned YouTubeKit path is not intrinsically a small-memory alternative. `SignatureSolver` owns a VM/context and original player; each batch JSON-encodes the complete source into `swiftInput`, the Unlicense helper parses a complete AST, emits nearly the complete modified player, then dynamically compiles it. Metadata requests run concurrently but signature solves run sequentially; repeated full-player work, not concurrent solver count, is source-supported. These lifetimes are plausible contributors to the earlier 256/512 MiB diagnostic failures. The exact allocation split of those historical runs remains unmeasured; this report does not attribute their entire RSS to one object or to networking.

Merely moving the full AST to native code was insufficient: initial whole-tree Tree-sitter attempts reached both 64 MiB and the explicitly authorized 96 MiB native working limits. Both returned typed `memory_limit` and zero live tracked allocations. Those failed receipts remain. The successful implementation changes the amount of syntax retained, not the process/JS budget.

## Native preprocessing contract

`p0_parser.h` exposes `p0_player_reduce(input, length, limits, output, capacity, result)` with caller-owned buffers. It performs no network access or player execution and retains no tree/context after returning.

1. Validate a bounded IIFE header with Tree-sitter.
2. Parse 64 KiB syntax windows, expanding only up to 256 KiB for an individual long statement. Accept explicit statement boundaries only after independently reparsing the complete prefix without any error/missing nodes. Recovery/EOF/ASI output is not itself a boundary.
3. Retain only declaration byte spans and keys. Release each window tree before moving on.
4. Match the same current upstream solver shape (URL constructor plus `set('alr','yes')`, matching parameter pattern) and timestamp property. Missing/ambiguous solver targets fail closed.
5. Reparse only selected initializers to collect conservative dependencies, lexical bindings and prototype alias groups. Emit the reduced IIFE in original source order.
6. Dispose all native allocations. Feed the reduced text to the unchanged pinned upstream analyzer/extractor with side-effect initializers disabled. Only that extracted solver may enter the network-free isolated evaluator.

Defaults: 4 MiB input, 64 MiB native working allocations (including bookkeeping), 256 KiB output, depth 256, five-second monotonic deadline. The native arena is separate from the unchanged JS heap; measured native peak is about 7.4 MB. Input/output caller buffers are reported separately and included in process RSS observation. `parse_ns` is accumulated syntax-parser time; `reduce_ns` is total preprocessing time including parsing, so the two must not be added.

Tree-sitter's default allocation failure aborts. This wrapper uses a counted allocation list and a **C-only setjmp boundary**, then frees every owned allocation and restores the exact previous allocator callbacks on every exit. No Swift/ObjC/C++ frame or destructor is crossed. Concurrent calls reject with `BUSY`; the P0 owns its linked Tree-sitter instance and must not share it with unrelated concurrent Tree-sitter callers. Host cancellation may use the callback to read a host-owned atomic flag; the optional signal flag is for a signal handler, not unsynchronized cross-thread writes.

This deliberately supports the tested player wrapper and bounded statement shapes. Unrecognized wrappers, an individually oversized statement, excessive nesting, ambiguous targets or unsupported syntax return typed failure. It is not a complete arbitrary-JavaScript rewriting service. A new player hash must be revalidated; a cache key should include the full player hash, upstream version and native extractor revision, rather than only a player ID.

## Failure evidence and remaining gates

- Whole-native-tree 64/96 MiB cap failures are preserved.
- Early window prototypes exposed a missing null-node guard and a recovered/ASI boundary problem. The local native crash/failed receipts are retained; the final implementation guards absent fields and independently validates explicit complete prefixes. Repeated malformed→valid and long-window cases pass in the same process.
- Independent read-only review identified cancellation arriving during the final dependency/emission phase. The final implementation checks periodically and again before success publication; a late-cancellation regression requires cleared output, zero live allocations and successful subsequent reuse. The reviewer rechecked that the late C jump restores callbacks without recursive cleanup.
- A minimal full-player QuickJS diagnostic, with a 64 MiB cap, crashed in `JS_DefineProperty → build_backtrace → JS_CallInternal`. It predates completion of the diagnostic host's scoped `structuredClone` helper. The exact crash cause and graceful resource-failure behavior require the coordinator's corrected-embedding/runtime investigation. Do not convert the passing reduced extraction into a broader QuickJS OOM-safety claim. Sanitized stack only; raw OS crash reports are not copied.
- Two initial JSC reference runs lacked `structuredClone`, required by Meriyah's Identifier/StringLiteral copying. The final reference uses the same plain-record JSON clone as the original P0 shim and passes. This is not a claim of full Web `structuredClone` conformance.
- No live provider challenges, authenticated data, signed media URLs, request headers or media bytes are stored in this package. Solver smoke inputs are synthetic. Complete source continuity/decoding, provider capability handling and corrected locked-device instrumentation remain separate coordinator-owned gates.

## Dependencies and build

- YouTube.js 18.3.0: MIT; Meriyah 7.4.2: ISC. Read from the coordinator's verified active `source/v2-integration/deps/node_modules` copy. The first diagnostic build read the pinned retired dependency tree without modifying it; subsequent build tooling uses the active copy.
- QuickJS 2026-06-04: MIT, the original P0 pin. Runtime safety triage is separate; this result does not approve it for production.
- Tree-sitter v0.25.10: MIT; archive SHA-256 `ad5040537537012b16ef6e1210a572b927c7cdc2b99d1ee88d44a7dcdc3ff44c`.
- tree-sitter-javascript v0.25.0: MIT; archive SHA-256 `9712fc283d3dc01d996d20b6392143445d05867a7aad76fdd723824468428b86`.

The grammar/runtime are built from the pinned public C sources, with no global installation. `bootstrap.py` verifies archive hashes and refuses to overwrite an existing source tree. MIT/ISC/Unlicense primary references were inspected; no BitChord GPL code or tests were copied. Third-party notices are retained with the manifest.

Run every build/probe through `engineering/p0-2026-11-10/run_guarded.py --allocation source`. This subtask has a 400 MiB scratch limit inside the shared 1 GiB source allocation, a 256 MiB observed process ceiling, and a 40 GiB actual-free floor. `run_bounded.py` additionally enforces a 20-second diagnostic deadline and sanitized output limits. Runtime bytes never use npm, Node, a subprocess JS engine, or a WebView; esbuild is a build tool only.

Build order on the pinned task checkout: `bootstrap.py` on fresh scratch, `build.sh`, then `build_quickjs.sh`. The native CLI accepts the full player and reduced output paths. The QuickJS phase CLI accepts the extraction bundle, reduced source, solver output path and `extract`. `parser-tests` accepts the full fixture to include concurrent-call checks. `build_reference.sh` creates the optional JSC comparison host. `build_ios.sh` builds an arm64 iOS static library; compilation is not device execution, and this agent did not deploy or request a phone test.

## Retention and handoff

All successful and failed sanitized receipts are copied into `evidence/`; `manifest.json` records exact current source/artifact hashes and scratch ownership. `evidence/reproducer-pre-clone.js` reconstructs the initial minimal diagnostic input before the documented helper addition; the actual unchanged `quickjs_phase.c` and binary hashes are retained. Only sanitized symbol/type summaries are copied from the two exact local crash reports; OS-managed reports remain untouched. Retain the full current fixture, reduced source, solver, pinned native sources and minimum native objects for the active coordinator integration. There are no large compiler/download caches to preserve as evidence. Duplicate reviewed/reference outputs and the JSC reference executable become recoverable-cleanup candidates once comparison is recorded; root coordinates that cleanup together with the active integration. No files were irreversibly deleted and this agent claims zero recovered bytes.

Primary sources: [YouTube.js player/extractor](https://github.com/LuanRT/YouTube.js), [pinned YouTubeKit source](https://github.com/alexeichhorn/YouTubeKit/tree/7f75a2299dc329c0b7855afb25d47663a02855cb), [Tree-sitter C API and allocator](https://github.com/tree-sitter/tree-sitter/tree/v0.25.10/lib), [JavaScript grammar](https://github.com/tree-sitter/tree-sitter-javascript/tree/v0.25.0), [QuickJS embedding/resource limits](https://bellard.org/quickjs/quickjs.html).
