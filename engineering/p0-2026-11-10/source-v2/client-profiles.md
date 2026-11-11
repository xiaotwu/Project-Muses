# Public Samsung profile adapter

This independently implemented MIT module models one existing unauthenticated
YouTubeKit client. It does not demonstrate that the request is accepted, that a
URL is playable, or that any earlier 403/authentication result is resolved.

`TV_SAMSUNG_PROFILE` pins YouTubeKit commit
`7f75a2299dc329c0b7855afb25d47663a02855cb`: TVHTML5 `5.20260707`, client header ID
`7`, Samsung `UKS9800`, Tizen `2.4.0`, and the exact upstream Samsung user agent.
This differs from YouTube.js 18.3.0's TV/Cobalt `7.20260311.12.00`. The adapter
never changes YouTube.js constants or adds/rewrites a signed URL's `cver`.

`buildPublicSamsungRequest({videoId, signatureTimestamp, visitorData})` returns
only `{url, method, headers, body}`. The two allowed IDs are the existing public
Blender samples `aqz-KE-bpKQ` and `eRsGyueVLvQ`. The signature timestamp is
optional and omitted when unavailable. The optional visitor value is public
watch-response context supplied by the caller; it is never discovered from
cookies or accounts. With no value, the header is empty as in the pinned
upstream. Samsung's profile UA overrides the generic watch-page UA upstream.

The request includes `html5Preference: HTML5_PREF_WANTS`, the upstream
`contentCheckOk`/`racyCheckOk` fields, and its client identity headers. These
fields are not treated as permission to access restricted content. The Samsung
profile has no API key, player `params`, embed/third-party context, encrypted
host flags, OAuth, proof token, cookie, or arbitrary header option. Unknown
request options and header control characters are rejected. No other client
profile or challenge-response behavior is synthesized.

`normalizeSamsungMetadata(raw, {videoId, receiptUnixMs, availability})` returns
`state: metadata | unsupported | invalid`. Only `playabilityStatus.status: OK`
and the requested video ID proceed to format normalization. Authentication,
challenge and other nonplayable statuses return no media candidates. Malformed
root metadata is invalid. Both normal and adaptive arrays are preserved as
separate occurrences, with source index, numeric itag, MIME type, safe numeric
length/duration/audio fields and optional audio-track identity. Protected and
malformed formats appear in bounded typed rejection entries.

Each result and format retains the same frozen profile provenance. URL and
cipher strings are copied **verbatim**, without decoding or deciphering;
`url_reference` is not a claim that n/signature processing is unnecessary.
Raw advertised `expiresInSeconds` is preserved without calculating a deadline.
The supplied availability result is carried unchanged, including unknown/null;
the caller must enforce it before media I/O. HLS, SABR and onesie references
remain separate fields and are not converted to direct media URLs. An empty
format list can still be valid metadata, never complete transport proof.

There are at most 256 format occurrences, 32,768 UTF-16 code units per stream
reference and 4,096 for other consumed text. Numeric values must be nonnegative
safe integers; unsafe lengths are rejected rather than truncated. The caller
continues to own raw HTTP size, native network allowlists, response receipt
time, signed URL lifetime, availability, deciphering, complete transfer and
decode/seek checks. The module performs no I/O and creates no shared cache.

Primary source attribution: YouTubeKit (MIT),
`Sources/YouTubeKit/InnerTube.swift:13–60,77,106–115,157–182,232–301` and
`Sources/YouTubeKit/Extraction.swift:152–179` at the pinned commit. The profile
values and wire-field names follow that schema; implementation and synthetic
tests are original. The optional remote extractor is not used. No GPL BitChord
implementation is copied.

Run `client-profiles.test.mjs` through the frozen guard with allocation `source`.
Node is solely a deterministic test tool, not an application runtime. A future
bounded native request is a separate coordinator-owned decision and evidence.
