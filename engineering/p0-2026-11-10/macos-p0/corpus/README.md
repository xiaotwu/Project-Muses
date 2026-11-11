# macOS P0 corpus and measurement campaign

Status: **tools prepared; corpus and campaign are draft, not frozen**. There are
33 distinct proposed public source identities, zero corpus entries with verified
media decode/native submission/audible identity, and zero real performance attempts. This directory is
independent MIT engineering code. It does not modify the production app, read a
user library/account, download media, or establish production backend integration.

## Draft material

`corpus.draft.json` contains stable IDs, canonical source pages, title/artist
observations, proposed media/version labels, explicit unknowns, and the next
evidence needed. Source title/catalog observations were read on 2026-11-10 using
public primary pages. The search/browser service sometimes returned cached page
titles: these are identity leads, not fresh origin availability or total-duration
verification. No credentials, headers, signed media URL, raw ad body or media file
were retained. Short factual metadata is independently selected; no playlists,
implementation or tests were copied from BitChord.

Coverage is **proposed**, not accepted:

| Coverage | Candidate cases | Remaining evidence |
| --- | --- | --- |
| Same-title collisions | Hello C001/C002; Stay C003/C004; Hallelujah C005/C006 | Confirm exact recordings/versions by listening; prohibit automatic title substitution. |
| Version families | Take On Me C008–C010; Get Lucky C011–C013 | Studio/live/edit and original/radio edit/remix labels exist; verify actual recording relation and timeline differences. |
| MV versus audio | C007/C008; C023/C024 | Independent IDs; extra intro/dialogue/edit equivalence remains unknown. |
| Language and character shapes | Japanese C015–C020; Chinese C021–C025; Latin titles throughout | Mixed-script, case/punctuation and same-title conflict candidates; metadata is not audible identity. |
| Long podcast/chapters | C026/C027 | Publisher chapter outlines exceed one hour; total duration and onset remain unmeasured. |
| Media variants | C028/C029 connect to earlier P0 probes | Earlier complete transfer/decoder evidence is separate; this corpus does not infer its own audition, source capabilities or onset from it. |
| Negative cases | N001–N005 | Missing/removed, authorization, region/account, expiry and invalid cache each have an expected error/recovery. Restricted IDs are deliberately unselected, not fabricated or fetched. |
| Queue occurrences | Collection plus Up Next repeats C001 | Distinct occurrence IDs, middle start, next/previous and unavailable skip still need execution. |

At least 30 identities require complete verification before a frozen comparison.
The draft first-30 plan is a scheduling demonstration, **not** approval of those
30 as the low-silence main group. All durations, onset lengths, current account/
region availability and corpus format/sample-rate observations remain unknown.
Short-content selection, two actual sample rates, positive/negative verification,
and recording/timeline review are explicitly open. Do not promote an unknown or
`page_title_observed` row simply because a URL resolves or metadata exists.

Primary observations include the official pages for
[a-ha studio audio](https://www.youtube.com/watch?v=HzdD8kbDzZA),
[unplugged](https://www.youtube.com/watch?v=92SGEe8l2Ng),
[unplugged edit](https://www.youtube.com/watch?v=jg5mXCCbd0U),
[Daft Punk album audio](https://www.youtube.com/watch?v=4D7u5KF7SP8),
[radio edit](https://www.youtube.com/watch?v=Rgrt_8mXrK8), and
[artist remix](https://www.youtube.com/watch?v=NnC2MtBSdsg).
The second MV/audio pair comes from the
[movie MV](https://www.youtube.com/watch?v=_sQSXwdtxlY) and
[official audio](https://www.youtube.com/watch?v=YD9r_tTtlaA).
Publisher pages provide the exact embedded IDs and chapter outlines for
[podcast #419](https://lexfridman.com/sam-altman-2/) and
[#400](https://lexfridman.com/elon-musk-4/); no linked audio was requested.
Every case keeps its own primary reference. Failed/throttled title observations
remain `unknown`. An initially mistyped ten-character Rick Astley ID was caught
by validation and corrected; the corrected ID still awaits metadata verification.

`campaign.draft.json` binds the canonical corpus SHA-256, baseline/candidate,
environment, measurement calibration, conditions and a 200-entry paired plan
(100 per build, 30 proposed identities, at least three each). Identity order is
balanced and shuffled by the frozen `random_seed`; AB/BA build order alternates.
The validator recomputes this order and checks actual starts against it. The
original 0.6.3 ZIP/executable hashes were read locally. A separate isolated
derivative is now [prepared but not launched](../baseline/preparation-receipt.json):
derived main SHA-256 `366d203977db620402f0b77f997874787f22c198b9fb5f0cf7dcc4f74e23b0ae`,
37 compiled sections unchanged, strict signature checked. This is preparation
evidence, not a run or a frozen baseline/candidate comparison. Candidate,
dependency/patch manifests, capture chain and calibration are not yet frozen.
Existing `source-v2` prototypes are not treated as a production macOS candidate.

## Independent identity and media evidence

Read `cases[]` by `case_id`, then `source.provider`, `source.id` and `source.page`.
These are stable identity inputs; `metadata.title` is a label, never a lookup key
or an instruction to silently substitute a similar recording. Validate the JSON
before selecting a case. The manifest's canonical digest is `campaign.digest`
(sorted compact UTF-8 JSON); the file-byte digest is recorded separately.

| Observation | Fields | What it establishes |
| --- | --- | --- |
| Metadata | `metadata.state`, duration, evidence | A page/catalog observation is distinct from reviewed `verified` metadata. |
| Transport | `checks.media_transport` | State, extent (`initial_segment`, `range_continuity`, `complete`), received/expected bytes, evidence. Complete requires matching positive expected/received lengths. |
| Decode | `checks.media_decoded` | State, extent (`initial_segment`, `complete`), actual codec/container/sample rate/channels, decoded frames, evidence. Initial decode does not imply complete decode. |
| Native submission | `checks.native_output_submitted` | Decoded frames consumed, frames submitted, post-gain/post-mute nonzero frames, mute state, evidence. Muted output must have zero post-mute nonzero frames. |
| Audibility | `checks.audibility` | Separate actual listening confirmation; a decoder/output callback cannot set this state. |
| Content identity | `checks.recording_identity` | Separate confirmation that the heard recording/version matches this source, not merely that sound exists. |
| Sound onset | `onset` and the campaign's output capture | Known natural silence is corpus evidence; per-attempt actual `t_sound_ms` is independent measurement evidence. |

Every stage starts `unknown`, and `failed` observations also require evidence.
There is no `playable` boolean or legacy `checks.playback`; that ambiguous shape
is rejected. Counters are reported per stage, with complete transport/decode
counted separately. Passing a stage never upgrades another stage. Positive-group
readiness requires all stages, confirmed audibility/content, metadata, onset,
capabilities and reviewed conditions. A reviewed initial segment can establish
initial playback eligibility with the other confirmations; it does **not** assert
complete media delivery, uninterrupted full playback or endurance.

For the next bounded native AVIO check, load a candidate's stable ID and produce
an append-only **stage receipt** outside this draft: corpus canonical/file SHA,
`case_id`, source ID, probe binary SHA, client/profile version, public player
input/reduced hashes, observation time, stage, extent and the numeric fields above.
Record actual codec/container rather than infer it from the requested format.
Keep expected/observed byte counts, resource limits, cancellation and failure
reason; retain an initial decode as initial even if the rest was never requested.
Bind a receipt's digest/reference into only the observed stage during a subsequent
reviewed corpus revision. No command here merges receipts or auto-promotes claims.
Public metadata and native silent output may be checked before listening; both
audibility and content identity remain unknown until separately observed. Signed
URLs, headers, cookies, raw player payloads and media bytes do not belong in these
receipts. The 33-row list is a frozen **draft artifact**, not a frozen acceptance
corpus and not authority to download or retain every listed work.

## Commands and scope

Python standard library only; Node and external services are unnecessary.
Every test/generation invocation uses the frozen parent guard with allocation
`source`. Set `PYTHONDONTWRITEBYTECODE=1`, and point `TMPDIR` to the existing owned
directory `/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/macos-corpus`.
The subbudget is 128 MiB, within the shared source 1 GiB / task 8 GiB budget;
the actual free-space floor remains 40 GiB. Tests refuse a different temp root.

Invoke each command after `run_guarded.py --allocation source --timeout 30 --`
and the environment settings above, using absolute paths:

```text
python3 campaign.py validate-corpus corpus.draft.json
python3 campaign.py validate-campaign campaign.draft.json corpus.draft.json
python3 campaign.py validate-campaign campaign.draft.json corpus.draft.json --require-frozen
python3 campaign.py append /owned/scratch/attempts.jsonl /owned/scratch/new-event.json
python3 campaign.py summarize campaign.json corpus.json /owned/scratch/attempts.jsonl
python3 test_campaign.py
```

Validation prints structural errors and separate `freeze_gaps`. A well-formed
draft exits 0 but remains `freeze_ready:false`; `--require-frozen` exits 2 for it.
No command automatically freezes a manifest or upgrades an evidence state.
`seed_draft.py OUTPUT_DIRECTORY` reproduces the two draft JSON documents, refuses
to overwrite either existing file, and performs no network requests. The schema
and concrete examples are the JSON files and the functions in `campaign.py`.

Before a real run, the coordinator must verify referenced evidence and freeze
the approved corpus, exact binaries/dependencies, environment, calibration and
cleanup plan. The validator checks required evidence references/digests/times;
it does **not** certify the truth of a manually supplied receipt. A new binary,
corpus, threshold, output chain or protocol requires a new campaign. Account and
network conditions must be explicit; system caches can remain honestly unknown.

## Attempt journal and statistics

Append one `start` record at the original OS input event, then one `finish`.
`append` assigns a sequence and previous-record SHA, uses an exclusive file lock,
appends without rewriting, and flushes to disk. The hash chain detects missing/
changed/reordered records when checked against a retained endpoint; it is not a
digital signature or protection against rewriting the entire journal and its
endpoint. Retain the campaign hash and endpoint with the coordinator receipts.
Base starts must follow the exact frozen `attempt_plan` order, including its
AB/BA sequence. Only one attempt may be in flight. Out-of-order or overlapping
valid-shaped events remain in counts and the retained journal, with explicit
issues blocking any performance conclusion. A missing finish remains unfinished;
it does not permit the next start to be treated as a valid serial run.

A start includes `attempt_id`, `case_id`, `build_id`, `stratum_id`,
`campaign_sha256`, actual `conditions`, `clock_id`, and `t_action_ms`. Conditions
record process, resolution, media, prefetch, connection, metadata, OS cache,
account, network, route, sample rate, app gain/mute, foreground, environment and
measurement identities. A finish includes its outcome, `retry_count` and
`end_conditions`. An actual success additionally requires `t_sound_ms`, the same
clock, `onset_kind:actual_output`, target-content confirmation, the same source
identity, measurement/calibration identity and bounded evidence reference.
Synthetic fixtures in `test_campaign.py` show complete records; their evidence
labels are explicitly synthetic and must never be used for a real campaign.

`t_first_byte`, `t_pcm_ready`, `FILE_LOADED`, device start and output callback
counts cannot replace `t_sound_ms`. No sound/incorrect source/unverified onset
cannot become success. Internal retry time remains measured from the original
action. A new click needs another attempt; a duplicate finish is a validation
error, not replacement of the old outcome.

All started attempts remain visible, including source rejection/change, network
error, timeout, wrong recording, cancellation and manual intervention. Unfinished
starts and unstarted planned entries prevent a complete conclusion. Actual hot/
cold, cache, account/network/route or other condition differences produce separate
groups. A mismatch with the frozen plan, or a condition change during an attempt,
blocks a comparable performance conclusion and remains in the report.

Only evidenced capture failure or unsynchronized clocks may be measurement-invalid.
One fixed-policy `.replacement1` attempt can be appended **after every base-plan
attempt has finished**, serially under the same frozen plan conditions, linked
with `replacement_for`; a player/network failure cannot
be replaced this way. Original invalid attempts stay visible and in all-started
counts. An unresolved or repeatedly invalid attempt keeps the campaign incomplete.

Nearest-rank p50/p95 use all valid-measurement attempts, assigning positive infinity
to valid attempts without verified target sound (serialized as `"infinity"`).
Only genuine measurement-invalid entries are excluded from latency quantiles;
all-started success rate and its descriptive Wilson 95% interval still retain
them. Successful-only quantiles are separately labeled. Draft, incomplete,
unfrozen, uncalibrated, malformed or incomparable campaigns never receive a
performance conclusion. Passing synthetic tests is not a listening, latency,
route, four-hour endurance or product acceptance result.

JSON inputs are bounded to 2 MiB per manifest, 16 MiB / 10,000 records per journal,
64 KiB per event, depth 24 and bounded strings/collections. Duplicate JSON keys,
nonfinite numbers and explicit sensitive credential/media fields are rejected.
CLI outputs never echo malformed field values. Evidence/scratch disposition is
recorded in `evidence.json`; no compiler cache is created or archived.
