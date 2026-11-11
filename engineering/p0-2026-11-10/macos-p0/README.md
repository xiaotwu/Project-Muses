# macOS P0 continuation

Status: **in progress, no production application integration**. The user deferred
the next iPhone run and asked to continue macOS P0. The corrected signed iPhone
candidate remains available without further device operations.

| Work | Current evidence | Remaining gate |
| --- | --- | --- |
| [0.6.3 baseline](baseline/README.md) | Fresh metadata-isolated derivative, strict signature and unchanged 37 compiled sections; no personal data seeded | Empty runtime preparation, actual-output measurement calibration, then the frozen comparison campaign |
| [Corpus and campaign](corpus/README.md) | Draft public identities, coverage and attempt schedule; bounded validation and failure-inclusive statistics | Each positive identity, capability, onset, recording relation and actual sound must be verified before freeze |
| [Static relink proof](relink/README.md) | Exact FFmpeg rebuild, observable replacement library, unchanged application objects, re-link/sign/run, AAC/Opus and muted native regression | Shipping-application packaging, release-specific source/objects and distribution review remain separate |
| [Acoustic calibration](calibration/physical-evidence/PHYSICAL-RESULT.md) | 46 offline checks; two physical summaries were invalid because the markers were not matched. The user later reported hearing two short beeps, without identifying a specific run. Capture is stopped | Qualitative hearing does not establish detector accuracy; total physical error remains unknown, and no first-sound score is available |
| [Native streaming output](streaming/README.md) | Eight local cases and a public AAC → freshly resolved AAC transition passed with muted output; PCM and callback consumption began after each first 256 KiB, RSS peaked at 97,370,112 B, workers/handles were released | Full EOF/decoder/resampler/ring drain, public Opus streaming, consistent deployment-target builds and physical output remain separate checks; the continuation is not production integration |

The [measurement protocol](../contracts/validation-protocol.md) remains the
authority for the 30-item playable corpus, cold/warm/account/network separation,
100 attempts per build, real-output timestamps and unchanged thresholds. Draft
tools or isolated component passes do not close those gates. The first production
delivery target remains macOS; P1–P9 are not advanced by this directory.

`stage-budget.json` binds the baseline/corpus/relink subbudgets to the original
8 GiB scratch and 40 GiB actual-free-space floor. The separately frozen
`calibration-budget.json` and `streaming-budget.json` add bounded suballocations
inside the same original parent limits, rather than enlarging those limits.
No SDK or shared dependency is duplicated. Failed preparations and executions
are retained. [Stage 5 cleanup](cleanup/EXECUTION.md) retires the expanded relink
compiler work while preserving the minimum reproducible replacement kit.
[Stage 6 cleanup](cleanup/STAGE6.md) retires superseded streaming and calibration
builds, preserving the current kits and the paused calibration app.
