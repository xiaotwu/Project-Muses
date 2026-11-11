# Advertised stream availability

`extractAvailability(rawPlayerJson, receiptUnixMs)` accepts a decoded raw player
JSON object and the integer Unix-millisecond receipt time captured before
`VideoInfo` parsing. It returns an immutable object with `state`,
`availableAtUnixMs`, `waitMs`, `reason`, and `prerollCount`. It does not mutate the
response, sleep, perform I/O, or assess playability/authentication/HTTP 403.

`known` describes only a delay advertised by the recognized response schema.
Missing or empty ad arrays yield zero with `reason: no_advertised_preroll`; this
does **not** establish that the provider accepts media now. `unknown` always has
null deadline/wait and must be handled before requesting media. The integration
layer binds the result to the same client, recording, format/itag and URL expiry.

Recognized structures are web before-content slots with direct or sequential
player-bytes layouts, and TV start placements with a direct ad or linear
sequence. The explicit layout-entered slot trigger and end placement are
excluded. A TV `AD_PLACEMENT_KIND_MILLISECONDS` placement is outside the initial
preroll only when `adTimeOffset` is a bounded object with both offsets present:
`offsetStartMilliseconds` must be a safe integer strictly greater than zero;
`offsetEndMilliseconds` must be the end-of-content sentinel `-1` or a safe
integer greater than or equal to the start. Numbers and complete decimal-digit
strings of at most 16 digits are accepted (plus the exact end sentinel `"-1"`).
Zero/negative/missing/nonfinite/fractional/unsafe or malformed offsets remain
unknown; node/container budgets still apply. This models initial playback at
content time zero, not seeking/resuming inside an ad range or servicing midrolls.
Other unknown eligibility values are not guessed. A skip offset wins
over a valid declared duration; otherwise `playerVars.length_seconds` supplies
the duration. Fractional seconds have at most millisecond precision. Missing,
negative, nonfinite, duplicate, conflicting or malformed timing is unknown.

Both web and TV preroll branches may represent the same ads. Without an
occurrence identity contract the parser returns
`ambiguous_preroll_representations`; it neither double-sums nor deduplicates by
duration or creative identity. Explicit sequential occurrences within one
representation are summed even when their timing is identical. `prerollCount`
counts observed recognized ad occurrences, capped at 64; on unknown results it
is a bounded diagnostic count, not a complete inventory.

The exported limits cap visited depth (24), structures (2,048), container
entries/query pairs (64), ad occurrences (64), short consumed strings/query keys
(4,096 UTF-16 code units), declared duration (one hour), and total selected wait
(**120 s**). `playerVars` alone has a separate **128 KiB UTF-8 byte budget**;
recognized `length_seconds` raw values are capped at 64 code units before
decoding. UTF-8 bytes are counted without allocating an encoded copy, including
paired/unpaired surrogate accounting.
The caller's operational waiting ceiling remains **20 s**. Receipt/deadline
values must be safe integer milliseconds within JavaScript's Date range. The
caller separately bounds the raw HTTP response before JSON decoding; this
module does not claim a byte or heap limit for an already allocated input.
Repeated object references/cycles and accessor properties are not decoded JSON
and are rejected on visited paths. No unknown branch is recursively explored.

Long strings under unrelated `videoDetails` or `streamingData` are not visited.
`invalid_string` is emitted only for consumed `triggerEvent`, placement `kind`
or ad `playerVars`/query keys, including missing/non-string eligibility values. Do not infer
that this error came from a media URL or unrelated metadata.

For a diagnostic probe, call `diagnoseAvailability(rawPlayerJson, receiptUnixMs)`.
It returns `{ availability, diagnostics }`; `availability` is identical to
`extractAvailability` and its existing result contract is unchanged. Diagnostics
describe consumed fields, using only the fixed categories
`web.trigger_event`, `tv.placement_kind`, `ad.player_vars`,
`ad.player_vars.key`, `ad.player_vars.length_seconds`, `ad.player_vars.pairs`,
a `valueType` and a numeric/null `stringLength`. Byte/pair bounds may additionally
report `utf8BytesObserved` or `pairCount`; these are bounded observed counts,
not unbounded total scans. For non-START/non-END placement kinds, `enumValue` returns
the complete kind string if it exactly matches
`^AD_PLACEMENT_KIND_[A-Z_]{1,64}$`; otherwise it is the fixed `unrecognized`.
Trailing newlines and any text outside this public schema enum shape are rejected.
For `MILLISECONDS`, the three fixed categories `tv.ad_time_offset`,
`tv.ad_time_offset.start_ms` and `tv.ad_time_offset.end_ms` additionally report
presence/type and, for each offset, string length and a safe integer numeric value
(otherwise null). Numeric conversion accepts only a complete bounded decimal
representation; accessors are never invoked. These rows appear on both valid and
invalid ranges. At most 64 placements are inspected, with four diagnostic rows
per `MILLISECONDS` placement; processing still stops at the first unknown result.
No other field value, query, URL, dynamic key or header is returned.
For example, the caller may emit `inspection.diagnostics` and then use
`inspection.availability` for its unchanged fail-closed decision. This is shape
evidence, not a causal explanation or permission to widen a bound. Logging an
unknown enum does not classify or exclude it: kinds other than the explicitly
validated `MILLISECONDS` contract remain unknown.

The coordinator's sanitized Sintel probe
`20261110T222650.042036Z-resolve_next-TV_SAMSUNG-aac.json` identified a real
`ad.player_vars` string of 97,203 code units. The former general 4,096-unit
string guard rejected that field; unrelated video metadata was not the cause.
The coordinator explicitly approved the separate 128 KiB field budget. Parsing
now scans the string once, never splits the whole query, and never copies or
decodes unrelated large values. Only bounded keys and the recognized bounded
duration value are decoded. Duplicate durations, 65 query pairs, oversized
fields, unknown/overlapping ad structures and timing/depth limits still return
unknown. This adjustment does not skip advertisements/waiting or enlarge the
64 MiB application JS heap. Complete real media behavior is verified by the
coordinator, not inferred from these synthetic fixtures.

This is an independent MIT implementation based on the schema documented in
YouTubeKit commit `7f75a2299dc329c0b7855afb25d47663a02855cb`,
`Sources/YouTubeKit/InnerTube+PrerollAds.swift:15–26,54–117` and
`Tests/YouTubeKitTests/ExtractionTests.swift:47–69`. Unlike that upstream parser,
unknown structures/timing are not converted to zero. No upstream implementation
or fixtures were copied. No relationship to the earlier IOS second-chunk 403
has been established.

The coordinator's sanitized receipt
`20261110T224053.655659Z-resolve_next-TV_SAMSUNG-aac.json` exposed the public enum
`AD_PLACEMENT_KIND_MILLISECONDS`. Its content-time semantics were independently
verified in the already retained public player script (2,658,728 bytes, SHA-256
`5f2035b38e20c1e57ad8e51ada9ea82d1eaac59f2a4603ebd851f421e3a3f5dd`):
line 2875 associates this kind with a content-offset trigger; line 2977 assigns
the midroll classification; lines 2981–2983 validate the start/end content-time
range and treat end `-1` as content end; line 5946 resolves that sentinel against
the content duration. Only schema/semantic observations informed the independent
validation contract above. No provider implementation or fixture was copied into
this MIT module. The pinned MIT YouTubeKit parser only filters START placements;
it does not by itself establish that every non-START placement is safe to ignore.

`availability.test.mjs` contains 115 deterministic synthetic fixtures, including
known zero, duration/skip sequences, duplicate representations, excluded midroll
and postroll, malformed and unknown values, resource limits, a 97,203-unit opaque
query value, encoded/duplicate timing fields, UTF-8 limits and large unrelated
metadata, strict enum diagnostic redaction, valid positive content-time ranges,
end sentinels, invalid offsets, accessors and retained preroll/overlap behavior.
The original 48 cases and the subsequent 77-case suite retain their expected
results. Run it through
the frozen guard with allocation `source`; Node is a test tool only and is not
part of the application runtime.
