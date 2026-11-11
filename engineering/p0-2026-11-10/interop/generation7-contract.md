# Generation-7 preservation contract

Audit base: Polyhymnia commit `7ce577588f3a8fdd4b8f31fc9c01b541291ffdd3`, `MusesSchema.generation == 7`. The inventory covers all **21 models and 227 stored declarations**, including relationship properties, plus queue value types and preferences. [The complete field map](generation7-field-map.md) gives every source property, declared type, nullability and proposed target; [the machine-readable map](generation7-field-map.json) also records source lines and SHA-256 for 24 owning/reference files. No personal database was opened, exported or changed. These are P1 migration requirements, not a claim that migration has been implemented.

## Identity and relationships

| Data | Required preserved identity and relationship | New-store rule |
| --- | --- | --- |
| Track | `id` UUID is the library identity; `youTubeId` identifies provider content. Different library UUIDs must not be silently merged merely because they share a provider ID. | Keep UUID, source kind + source item ID, metadata, likes, library membership, counts and timestamps. Preserve raw enum values, including unknown values. Missing `mediaKindRaw` projects as song; missing `libraryMember` projects as true. Do not rewrite nils before migration validation. |
| Local playlist | `Playlist.id` owns ordered `PlaylistItem.id` occurrences, each with optional `track`. | Playlist deletion cascades to its occurrences; Track deletion nullifies its link and retains the occurrence. Preserve name, pin, timestamps, order and duplicates. No local media-file import is introduced. |
| Provider playlist import | `YouTubeImport.id` is local import identity; `playlistId` and optional `accountChannelID` supply source/account scope. | Preserve soft-deletion timestamp, local title/artwork, last pull/check times, base/shadow revision IDs, writability and exact-target approval time. Deleting the import and deleting playable tracks remain separate commands. |
| Imported occurrence | `YouTubeImportItem.id` is the local occurrence; `playlistItemID` is the remote resource identity; `youTubeId` is content identity. | Never deduplicate by video ID. Preserve duplicate occurrences, order, unavailable/private/deleted placeholders and nullable Track links. Import deletion cascades to occurrences, not playable Tracks. |
| Track–release evidence | Unique `id` and `evidenceKey`; `trackID`, `releaseStableID`, optional source import/item IDs and source order. | Preserve every evidence edge and provenance. Multiple occurrences may justify the same track/release relation. A presentation projection may deduplicate; persistence may not. |
| Catalog releases/artists | Stable browse/playlist/channel identities, independent of display text. | Metadata caches are rebuildable; preserve source identity links and evidence separately. Cache eviction must not delete Track/user state. Legacy single-release Track columns are compatibility input, not the many-to-many truth. |
| Track notes | `id`, `trackId`, content, creation/update dates. | One note per track is a service invariant, not a declared unique constraint on `trackId`. Detect duplicate legacy notes and require explicit reconciliation; never select one and silently discard the others. |
| Bookmarks | Independent `id`, `trackId`, position, optional title/note and created date. | Preserve every bookmark and its order by position. **`timestampMs` stores seconds**, explicitly documented in `NotesService.addBookmark` and passed directly to `playback.seek(to:)` by `NotesSheets`. Map to `position_seconds`, not milliseconds. |
| Listening event | Independent `id`, track UUID, denormalized title/artist/album, actual listened duration, outcome and optional session ID. | Track deletion must not cascade into history. Retain events when the source Track is absent. Preserve unknown duration (`completionRatio == nil`), outcome, all dates and reserved context data. |
| Listening session | `id`, lifecycle timestamps/status, queue snapshot, Track UUID and checkpoint. | Preserve open/ended status and checkpoint. Its queue snapshot is audit context, not the only authoritative current queue. Do not auto-play merely because an active session was restored. |
| Podcast follow | `PodcastShow.catalogID` is source show identity. | Following/unfollowing remains local; migration must not mutate remote subscriptions. Preserve follow/update times and display metadata. |
| Podcast progress | `PodcastEpisodeState.videoID` owns shared progress/completed/played state. | Do not create separate progress for the same video in two shows. `showCatalogID` on progress is legacy association context; it is not the complete membership graph. |
| Podcast membership | Unique persisted `key`, plus `showCatalogID` and `videoID`. | Preserve all show/video pairs. P1 may use a composite unique key, but verify its equivalence with the existing serialized key; do not silently reconstruct ambiguous identities. |
| Custom EQ | `EQPreset.id`, name, bands JSON, created date. | Preserve custom presets and their IDs; built-in presets are code, not persisted rows. Resolve the active preset preference against imported IDs. Malformed custom bands must be reported, not silently replaced by flat during migration. |

All original UUIDs remain UUIDs in the production contract. The P0 interop fixture deliberately uses small numeric media/occurrence IDs to exercise the ABI without claiming to implement the production model. Target SQL columns in the inventory are logical proposals; final physical indexes/DDL belong to P1.

## Queue is a separate occurrence graph

The singleton QueueState has fixed UUID `00000000-0000-0000-0000-000000000001`. Import its fourteen fields in one transaction: current collection, collection cursor, explicit Up Next, history, repeat mode, shuffle, saved time, crash-recovery Track/position, groups, inserted current, Smart Shuffle and pre-shuffle order. Do not flatten collection, insertion and history into one list.

| Serialized value | Fields that must survive |
| --- | --- |
| `QueueItem` | `id`, complete `track` snapshot, `queuedAt`, `fromContext`, `locked`, `groupId`, `priority`, `historyState`, `historyRecordID`, `collectionAnchorID`, `recommendationSourceVideoID` |
| `TrackSnapshot` | `id`, title, artist, albumTitle, durationSeconds, youTubeId, artworkUrl, sampleRate, bitDepth, bitRate, channels, codec, isLossless, liked, lyrics, lyricsOffsetMs, replayGain, mediaKindRaw |
| `QueueGroup` | `id`, name, order, collapsed |
| `SmartShuffleState` | enabled, collectionID, collectionPlayed, countedOccurrences, playedVideoIDs, pending QueueItem |
| `originalOrderIDsJSON` | Ordered **queue occurrence UUIDs**, not Track UUIDs or provider video IDs |

`QueueItem.id` distinguishes repeated occurrences of one Track. A history record has its own `historyRecordID`: the same occurrence may be played repeatedly and generate multiple history records. Do not place a unique constraint on history's occurrence ID. Preserve the inserted-current item independently of the collection cursor, and keep its anchor for returning to collection playback.

Generation 7's pre-shuffle order is essential: toggling shuffle off ranks surviving collection entries by the saved occurrence order; newly added entries retain their relative order after those entries. Removed entries must not reappear. The current occurrence must remain current after reorder. Legacy missing pre-shuffle order falls back to current collection order, matching the existing restore implementation; record any such compatibility conversion in the migration receipt.

Migration must decode all queue fields before accepting any of them. A malformed queue or unknown incompatible structure is a validation failure, not an empty queue. Older missing/duplicate `historyRecordID` values require a deterministic migration mapping recorded in the receipt, rather than generating new IDs on every retry. Smart Shuffle's pending/insertion state and disabled-state cleanup require semantic comparison with `QueueService.restore`, not byte-level JSON comparison alone.

## Time, nullability and value representation

| Source fields | Existing unit/meaning | Import requirement |
| --- | --- | --- |
| Track/YouTubeImportItem `durationMs`; ListeningEvent `listenedMs`; Track `lyricsOffsetMs` | Integer milliseconds | Preserve signed values and exact integer precision; validate legal ranges separately. |
| QueueState `lastPositionMs`; ListeningSession `currentPositionMs`; PodcastEpisodeState `lastPositionMs` | Floating-point milliseconds | Preserve finite values; any conversion to engine seconds is explicit `/ 1000`. |
| TrackBookmark `timestampMs`; TrackSnapshot `durationSeconds` | Floating-point **seconds** | Preserve directly; rename bookmark target field. No inference from the legacy suffix. |
| Podcast `durationMs` | Optional integer milliseconds | Nil remains unknown, not zero. |
| Foundation `Date` | Date value with Foundation serialization epoch when JSONEncoder uses its default | Export a tagged timestamp representation and make the Foundation/Unix epoch conversion explicit in both Swift and C# fixtures. Do not interpret old JSON numeric dates as Unix seconds. |
| Enum `*Raw`, nullable Booleans, optional IDs and strings | Source values plus documented UI defaults | Store the original raw/null value; derive defaults in projections. Do not conflate nil, empty string, false, zero or unknown. |
| Revision `Data` and serialized JSON fields | Versioned structural evidence, not arbitrary rebuildable cache | Preserve original bytes/checksum through validation, plus typed decoded comparison. A decoder fallback must not erase evidence. |

## Pending sync is durable evidence

Four models carry the sync graph, all fully enumerated in the field map:

- `YouTubePlaylistRevision`: local/import/account ownership, revision kind, date, exact snapshot bytes, fingerprint and pin.
- `YouTubeSyncBatch`: base/local/remote revision IDs, expected remote fingerprint, desired and pre-remote snapshot bytes, lifecycle state/times and invalidation reason.
- `YouTubeSyncOperation`: unique idempotency key, import/account/batch identity, sequence, kind/state, exact remote occurrence/resource identity, source video, positions/neighbours, observed remote result, attempts, last error and lifecycle times.
- `YouTubePlaylistResourceOperation`: independent create/delete journal, optional import/remote target IDs, required account, requested title/description/privacy, expected remote fingerprint, pre-delete snapshot, attempts/error and lifecycle times. A create may not yet have a playlist ID.

Keep `planned`, `started`, `remoteObserved`, `locallyCommitted`, `needsConfirmation`/`needsReview`, `failed`, `discarded` as distinct states. Legacy item-operation raw aliases `pending`, `running`, `completed` are interpreted by current source as planned, started, locallyCommitted; preserve the original value and record any normalization. Unknown state strings fail closed for writes.

Imported/in-flight journals are **paused for reconciliation**, not automatically replayed after migration. A remote-observed operation might already have succeeded. Resume only after exact account and playlist identity, current remote snapshot/fingerprint and occurrence resources are reconciled with durable results. Ownership or OAuth scope does not replace the stored exact-target write approval. Keep local/base/remote-shadow revision distinctions and incomplete pagination metadata; never treat an incomplete remote playlist as a complete deletion set. No remote calls or writes are part of this audit.

## Outside the generation-7 model list

`UserPreferences.swift` still owns UI/theme/language, gestures/navigation, active EQ and bands, volume/last audible volume, output device, quality, lyrics choices, feature flags, sidebar playlist order, update preferences, and account/Home consent selections. Preserve relevant platform-native preferences using an explicit allowlist and a before/after manifest; do not dump the whole preferences domain into Rust. Consent-version/browser/account selections do not themselves grant new consent.

OAuth secrets remain native credential-store material. Browser cookies, temporary jars, account hashes, volatile continuation/session tokens and raw web payloads are not business-model exports. This audit did not read them. Existing artwork, stream prefetch and catalog caches are not an offline-download library. The new download ledger is a new capability for eligible sources, with its own total-size budget and source/account/quality identity; it must not be inferred from cached files or reinstate local-file scanning.

## P1 validation gate

1. Export logical values on the owning SwiftData context from a WAL-consistent source snapshot. Existing `StoreUpgradeSnapshot` demonstrates why `immutable=1` is unsafe for a live WAL; do not copy only the main SQLite file or infer SwiftData's private schema as the business contract.
2. Produce counts, ID sets, ordered occurrence lists, relationship edges, typed value hashes and source/schema versions for every model plus queue substructure. Keep only bounded receipts once validation is complete.
3. Import into a distinct SQLite store under a single writer transaction and versioned application/schema identity. Abort on unsupported enum/payload versions, missing required identity, malformed queue, unresolved duplicate note or relationship inconsistency. Preserve the source and failed receipts.
4. Compare likes, pins, notes/bookmarks, complete history/session data, podcast many-to-many membership and shared progress, all playlist occurrences/order, full queue + original order, and all pending sync journals. Use fixtures with duplicate videos, deleted tracks, unavailable rows, tombstones, interrupted writes, missing optional legacy fields, non-ASCII text, and seconds/milliseconds/date-epoch traps.
5. Cold restart the new app, exercise those behaviors through immutable snapshots, then atomically activate one store/engine owner. The source store is not renamed/deleted during validation. Legacy pipeline removal is a separately evidenced post-activation cleanup, following the user's recoverable-disposal rules.

The P0 synthetic core proves the interop/persistence boundary, but **none of this 21-model migration or user-store acceptance has run yet**.
