# Embedded-video interaction contract — P0

Status: implementation contract for the approved §3.4 / F15 direction; **no production UI has been changed or rendered by this work**. User-confirmed requirements are main-content embedding, no independent popup, preserved G1/F3 styling, a single playback authority, source-appropriate native/official visible video, safe timeline mapping, and fullscreen returning to the same embedded position. The concrete collapse/navigation/layout defaults below are P0 design proposals within that direction; they were not additional user questionnaire answers.

## Current source and replacement boundary

Read-only baseline: Polyhymnia `7ce577588f3a8fdd4b8f31fc9c01b541291ffdd3`; [source hashes](embedded-video-source-manifest.json).

| Current executable source | Preserve | Replace in P3 |
| --- | --- | --- |
| `PlaybackPresentation.video` calls `surface.float()`; row help says floating window | Explicit video intent and collection context; cancellable resolution | Route all entries to one embedded host; remove floating-window entry/wording. Selecting the same provider video in another queue occurrence must still respect its occurrence ID. |
| `VideoSurface` retains one native view and reparents it; `float()` creates an `NSPanel` | One session-owned view; no reload on presentation-only change | Remove the panel and floating/dock lifecycle. Expanded, compact and fullscreen are placements of the same main-window session. |
| `YouTubeVideoOverlay` is a modal scrim with hover controls | Aspect fit, loading/unavailable state, nonpersistent web data, chapter targeting and stop acknowledgement | Content-layout stage with persistent discoverable exit/return controls; no screen-covering modal scrim or hover-only essential action. |
| `VideoPlaybackSession` guards session, seek and volume revisions | Stale event rejection and pending play/pause intent | Unified Core session/occurrence/generation identity and explicit adapter acknowledgement. |
| `finishVideoSession` waits for WebKit pause acknowledgement before restoring native audio | Actual stop acknowledgement before changing sound owner | Generalize for native video and visible provider adapters; add validated timeline mapping and timeout states. |
| `NowPlayingManager` clears native metadata while provider WebKit owns a media session | One system media publisher/card | Make the publisher a capability of the current adapter, with the same owner lease as audible output. |
| `PlayerBar` primarily reads native `playback.state` | Familiar capsule, typography, command vocabulary | Shared session snapshot; never show a second conflicting audio transport while video owns sound. |

The current WebKit teardown calls `pauseAllMediaPlayback` before its stop callback. Sending a JavaScript pause command, hiding the view or changing a Boolean alone is not an equivalent acknowledgement. Source inspection establishes the intended boundary; it is not proof of audible silence on every provider/device.

## One session, orthogonal presentation and transport

`PlaybackCoordinator` owns `sessionID`, `queueOccurrenceID`, source/media identity, `generation`, desired play/pause intent, volume, rate, timeline identity, progress checkpoints and completion accounting. `VideoSessionAdapter` implements a source's supported video controls and reports acknowledged state. A view never controls an engine independently.

Presentation is `absent | expanded | compact | fullscreen(returnPlacement)`. Transport is `preparing | transferring | readyPaused | playing | buffering | unavailable | stopping`. Sound ownership is separately `nativeAudio | videoAdapter | none`; there is never more than one audible owner. Fullscreen and layout changes do not select another Track, enqueue another item, create another session, or advance a generation.

Every command/event carries `{sessionID, queueOccurrenceID, generation, adapterID, commandID}`; seek/volume revisions are additionally monotonic. The owner lease has its own transfer token. Late completions, timeouts, stop acknowledgements and old fullscreen callbacks may release their own resources, but cannot seek, resume, close or advance a replacement occurrence.

| State | Visible treatment | Enabled actions and ownership |
| --- | --- | --- |
| Preparing | Stable aspect-fit frame/poster, loading label, progress indicator; title and Close remain available | Play/pause and volume continue to control the current sound owner, alongside Cancel/Close, Return to audio and navigation. The current audio owner may continue while a video adapter prepares silently. Preparation cannot grant sound or expose an independently playable, ungranted video transport. |
| Transferring | Frame retained; concise switching indicator | Pause/Cancel/Close remain available. Other transport intents are coalesced by generation. No new owner becomes audible until the old owner acknowledges silence. |
| Playing | Picture and one control set; elapsed/remaining time reflects the active timeline | Play/pause, seek where supported, volume, next/previous, captions/chapters, layout/fullscreen and return/close. |
| Paused | Last frame/poster remains; Play is explicit | Same controls subject to source capability. A paused entry never autoplays because the embed becomes ready. |
| Buffering | Last valid frame/poster; buffering indication separate from paused intent | Pause, seek/cancel where supported, return/close. Buffering does not erase desired play intent or count as audible listening. |
| Unavailable | In-place source-appropriate explanation, Retry and Return to audio, persistent Close | No active hit-testing/accessibility for an invisible failed player. Retry starts a new adapter generation, retains occurrence/context, and never creates duplicate playback. |
| Stopping | Brief retained stage/transition while stop acknowledgement is pending | Close is idempotent; a new selection may supersede the old request. A timeout is visible and does not authorize a second sound owner. |

## Handoff ordering and timeline mapping

**Enter video:** resolve/preflight the requested source with the correct account scope; prepare one adapter silently; capture the most recent audio checkpoint at the transfer boundary; send `PauseAndDrain(audio, transferToken)`; wait for the native output's silence acknowledgement; apply a valid video timeline mapping and await its seek/ready acknowledgement; then grant the video lease and apply the latest saved play intent and volume. Audio can progress while video is preparing, so a position sampled only at the initial click is insufficient.

**Return/close:** revoke the video lease; ask its adapter to stop/pause and confirm silence; capture the last accepted video timeline position; prepare/seek native audio while silent; wait for audio ready/seek acknowledgement; then grant the native lease and restore the saved intent. Existing `resumeAfterVideo=false` means the restored audio remains paused. A user's later explicit pause/play updates the saved intent; a stale pre-entry autoplay flag must not override it. Ending/error/timeout alone is not an explicit Play command.

The sound handoff itself has no navigation side effect. A separate presentation request carries `{reason, targetRoute, navigationGeneration, focusReturn}`. User Close chooses the saved browsing route; Return to audio chooses current Now Playing; navigation to Settings chooses that requested destination. Complete that route/focus change only if its navigation generation is still current. A late stop acknowledgement can release old resources without sending the user back to an obsolete route.

For a visible provider embed, use the platform adapter's supported media-pausing acknowledgement (the current macOS prototype has `WKWebView.pauseAllMediaPlayback`). Provider state packets alone may lag; if the adapter cannot confirm silence, remain silent/unavailable and offer Retry or recovery. Do not resume native sound merely because a timeout expired, a frame disappeared, JavaScript evaluation returned, or the native view moved. Stop/ready/seek/transfer timeouts and forced teardown must be exercised on real platform builds before release.

| Timeline relationship | Entry behavior | Return behavior |
| --- | --- | --- |
| Same media timeline guaranteed by the adapter | Use the acknowledged current media time; clamp only to a known valid seek range | Map back identically; preserve pause/play intent. |
| Verified alternate-version mapping | Use a versioned mapping with source/target timeline IDs and valid segments | Apply the inverse only in an invertible valid segment; invalidate it if the source identity/version changes. |
| Unverified/different MV, live, remix, edit or intro | Start video at its own beginning and state that it is a different version; retain the parked audio checkpoint | Restore the parked audio checkpoint. Never reuse raw video seconds or attach audio lyrics to it. |
| Nonseekable/live source | Seek controls disabled with a clear live/nonseekable state | Resume according to that source's live policy; do not fabricate a stored VOD position. |

A matching title, artist or approximate duration is insufficient evidence for a shared timeline. A source video ID can identify content but does not by itself prove correspondence to a different audio rendition. Chapters, captions/lyrics, repeat ranges and bookmarks are keyed to their timeline; only mapped data may cross the boundary.

## Commands and control ownership

| Command | Required semantics |
| --- | --- |
| `OpenVideo(occurrence, context, sourceVariant)` | Reuse the current occurrence/session when it is the same request. A standalone video selected from a collection performs the normal explicit queue selection with that collection, not a shadow video queue. Preserve duplicate occurrence IDs. |
| `SetPlaying / Seek / SetVolume / SetRate` | One Coordinator command path from mouse, keyboard, accessibility, menu or system controls. Adapter feedback carries revisions; it cannot undo a newer intent. Unsupported capabilities are disabled, not emulated with a second engine. |
| `Next / Previous / SelectOccurrence` | Revoke/stop old owner, advance generation, update the authoritative queue once, then prepare the new source. If the next occurrence lacks video capability, return to its native audio presentation instead of inventing a video match or silently skipping it. |
| `SelectCaption / SeekChapter` | Apply only to the active source/timeline and its supported API. Chapters in a stale popover cannot seek a replacement track. |
| `Collapse / Expand` | Change main-content placement only; keep the same session, adapter, view and position. Never open a utility window or system picture-in-picture window. |
| `EnterFullscreen / ExitFullscreen` | Use the main window/platform content's fullscreen facility; retain prior placement, route, scroll and focus. On exit, reattach the existing surface at the same embedded slot. Fullscreen does not create another player. |
| `ReturnToAudio` | Request the acknowledged sound handoff plus a separate target of current cover/vinyl Now Playing. Apply that target only for the current navigation generation. Preserve styling, queue and saved intent/resume preference. |
| `CloseVideo` | User Close requests the safe sound handoff plus the most recent browsing route/scroll/focus. Its route effect is separate and generation-checked. Closing video is not queue removal, playback stop, rollback, or playlist deletion. |
| `DismissVideoForNavigation(targetRoute, navigationGeneration)` | Use the same sound handoff, then complete the explicit destination rather than Close's browsing-return behavior. A newer navigation request supersedes only the route/focus completion, not the obligation to stop the old sound owner safely. |
| `RetryVideo` | Cancel/release the failed attempt, preserve context, increment adapter generation and start one new attempt. Keep the parked checkpoint and saved intent until a successful new transfer. |

During preparation, retain exactly one visible control set for the current sound owner: keep the existing PlayerBar until its play/pause/volume controls have been rehosted into the stage, then hide the old set. Keep the new video transport non-playing/noninteractive until the owner transfer is acknowledged; a loading poster may occupy the frame. Pause during preparation updates the saved intent and pauses the current audio owner immediately. After video receives its lease, show only that adapter's active transport and hide the audio PlayerBar's transport. Put queue access in the embedded stage's native control group. Return the existing floating capsule only after the audio handoff completes, subject to its destination's normal visibility policy. Settings keeps its existing no-PlayerBar treatment.

For allowed direct video sources, the native stage owns one app control row: play/pause, timeline, volume, captions/chapters, fullscreen, Return to audio and Close. Once a source requiring its official visible embedded controls owns playback, preserve those controls unobstructed and suppress duplicate app play/pause/timeline/volume controls. Before that transfer, the preparation rule above keeps the current audio controls available. The surrounding native group still supplies queue, layout, return and close; supported keyboard/system commands route through the same adapter. This capability distinction must not produce two media cards or two sound paths.

`systemMediaPublisher` follows the owner lease: the app publishes for native audio/native video where supported; a provider-supplied system session owns its own publication where unavoidable. The other publisher and handlers are suspended before ownership changes. A second Control Center/lock-screen card is a failure, not an acceptable cosmetic difference.

## Proposed navigation and dismissal defaults

Collapse keeps the picture **visible inside the main content container** and reveals the existing browsing content below/beside it. It is a compact layout, not a floating overlay, bottom video well, mini-window or hidden web-audio mode. This gives users a way to browse without losing video while preserving the current single-window product direction.

- Browsing navigation (Home/Search/library/detail/back/forward) collapses an expanded stage to this visible compact region and updates the normal browsing history. It neither changes the playing occurrence nor resumes parked audio.
- Settings/other destinations that cannot accommodate the visible compact stage request `DismissVideoForNavigation(destination, navigationGeneration)`. The acknowledged sound handoff completes before the destination uses its normal layout; it must not execute User Close's browsing-return action. A short transition may be shown while the stop acknowledgement completes, and a newer destination invalidates stale route/focus completion.
- Back while expanded first collapses to the saved browsing context; subsequent Back/Forward follows ordinary browsing history. Fullscreen Back/Escape first exits fullscreen. Close returns to the latest browsing context; Return to audio opens the current audio Now Playing surface.
- Escape precedence: dismiss the foremost caption/chapter/menu/sheet; otherwise exit fullscreen; otherwise collapse expanded video; otherwise close compact video. A text editor or modal control retains its native Escape behavior first. The native View-menu actions use the same commands.
- In **every placement** (expanded, compact or fullscreen), pause an official embed and preserve intent/checkpoint when its surface becomes nonvisible: minimized/closed window, hidden or background mobile scene, or complete occlusion by a sheet/other content. A desktop application merely losing keyboard focus or active status while its video remains visible does **not** trigger this rule. Resuming requires a valid visible surface or an explicit safe audio handoff. Do not turn an official visible video into hidden background audio. Direct-source background behavior is a declared platform capability and must pass native lifecycle tests.
- Closing the main window closes the video session through its stop acknowledgement, then follows the app's separately defined background-audio policy. Quitting cancels work and stops all owned output; it cannot leave a helper/WebView playing.

## Responsive layout specifications

Breakpoints below are **proposed effective content-space thresholds**, after native safe areas, the existing 88-point navigation reservation and any queue pane. They are not fixed device classes. Preserve the actual source aspect ratio; use aspect fit with neutral/black letterboxing, never crop/stretch the picture to satisfy a card shape. G1 champagne-gold selection/focus, F3 title/track typography and existing native control materials remain; the picture has no decorative outer glass frame.

| Layout | Stage and information | Controls and queue |
| --- | --- | --- |
| Wide: content width ≥900 pt and height ≥600 pt | Expanded video occupies the primary column; a secondary 260–300 pt area can show chapter/details content. Title/artist/source status are below the picture, not a floating title strip on it. Fit height as well as width so controls never fall below the viewport. | Persistent native control group below the frame. Existing integrated trailing queue remains distinct; opening it recomputes effective width and may select the narrow layout. Compact mode uses a 320–400 pt aspect-fit picture beside title/controls at the top of main content, with browsing below. |
| Narrow desktop: content width <900 pt or constrained height | One column: picture, two-line title/metadata, controls, then chapters/details or browsing. Collapse removes secondary details and reduces the stage, but retains a readable visible picture. | Timeline has its own full-width row; transport/volume and presentation actions can use a second row. Captions/chapters use native popovers/sheets. If a full-height trailing queue would leave the picture unusable, show its content below the stage; keep current collection, Up Next and history distinctions. |
| Phone: safe content width <600 pt | Portrait picture spans safe content width, title may wrap to two lines, chapter/details list follows. Landscape/fullscreen fits both dimensions and returns to the same portrait/compact location. No miniature floating video window. | Touch actions have ≥44 pt hit targets; timeline is a separate accessible row. Keep Play/Pause, Return to audio and Close directly reachable; place low-frequency options under a labeled native menu. Captions/chapters/queue use native sheets while honoring visibility/pausing rules. A keyboard cannot cover the only exit/return action. |

Loading, paused, unavailable and retry content use the same allocated frame in every layout, so surrounding controls do not jump. Loading/error text is localized and readable at large text sizes. A failure view never hides its only recovery action behind hover. The source's mandatory controls remain inside the safe visible frame and are not covered by app buttons.

## Focus and accessibility

Record entry focus identity (button/row/occurrence), browsing route/scroll and last embedded placement. On entry, announce video loading and focus the stage's transport/summary region without stealing focus from an active text edit. The accessible order is title/status, picture/provider controls, app controls, chapter/details and queue. In compact mode, browsing follows the stage; offscreen duplicate controls are removed from accessibility, not merely made transparent.

Keyboard Tab/Shift-Tab reaches every enabled action and exits the stage. Space and seek shortcuts operate only when the content keyboard scope permits them, not while typing. Essential Close/Return/Fullscreen controls stay discoverable for keyboard and VoiceOver. Fullscreen exit restores the previously focused embedded control; Close restores the originating control if it still exists, otherwise the current track row or page heading. Never focus a removed occurrence.

Reduce Motion removes placement animation and preserves state; Reduce Transparency/high contrast replace glass with native opaque treatment and visible focus outlines. Position updates are isolated to transport/timeline presentation and do not invalidate library/browsing lists.

## P3/P5 acceptance scenarios

1. Enter from PlayerBar, search, duplicate playlist occurrences, MV and podcast chapter entry; verify one occurrence/context, correct saved play/pause intent and no popup.
2. Audio→video→audio while playing, paused, buffering, seeking and muted; record both output ownership and audible output. Check that neither hidden native output nor a second media card remains.
3. Simulate delayed/out-of-order ready, seek, pause, stopped and completion packets; immediately change tracks, close, retry or quit. Old generations cannot resume/seek/advance a replacement session.
4. Test same timeline, verified offset/segment mapping, different MV edit, unknown duration and live/nonseekable source. Verify chapters/lyrics/bookmarks never borrow an incompatible timeline.
5. Collapse, browse, Back/Forward, open Settings, resize with Queue, enter/exit fullscreen repeatedly, minimize/restore and return to audio. Check the same surface/session, route/scroll/focus, checkpoint and ownership policy.
6. Test rejected embed/autoplay, timeout, network loss, failed silence acknowledgement and repeated Retry. Recovery remains visible and queue/history do not duplicate.
7. Render wide/narrow/phone, short windows and large text in light/dark/high contrast; keyboard and VoiceOver traverse; Reduce Motion/Transparency preserve controls. A source-mandated visible player stays visible or paused.
8. Natural video end and concurrent stale native end signal advance once; changing presentation alone does not create a second listening event or double-count time.

These are required future checks, not completed runtime evidence. The P0 interop generation/lifetime proof supports the underlying boundary but does not validate this UI or an actual audio/video handoff.
