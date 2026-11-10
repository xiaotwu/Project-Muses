# BitChord 1.9.1 native reference observations

Observed 2026-11-10 in the official arm64 release APK, in a new Android 13 / API 33 AVD. This is a bounded black-box interaction record, not a BitChord reliability benchmark or evidence that Muses implements these features. No BitChord implementation or tests were copied.

## Provenance and isolation

- Official release: <https://github.com/kushagrasinghx/BitChord/releases/tag/v1.9.1>.
- APK: `BitChord-v1.9.1_arm64-v8a.apk`, 89,348,521 bytes, SHA-256 `31cdb3d402615ad0134906b28a2ecb13914e83147bd1a1e15d16050a8092d950`; matched the release digest. Android APK v2 signature verified; signer SHA-256 `b5895722346fe38636597d6e2e2ecb8d2963fc37b138d5527e525d699554d921`.
- Package `com.music.bitchord`, version code 39, minimum SDK 26, target SDK 36.
- Fresh task AVD `Muses_P0_BitChord_191`: 2 GiB RAM, 2 cores, 1 GiB data partition, no camera, no snapshots, **host audio disabled**. Existing SDK/system image reused; existing AVDs preserved.
- UI operated through Android Studio Running Devices using the computer-use API. The empty task IDE project was opened in Safe Mode; no Google IDE account was connected. One IDE onboarding notification was dismissed with “Do not show again”; this changed that notification preference. No device media/library permissions or account credentials were supplied.
- Onboarding nickname `Muses P0`; account connection explicitly skipped. This is not an authenticated account/sync test.

## Observed behavior and implications

| Path | Direct observation | Muses contract implication |
| --- | --- | --- |
| Anonymous entry | Account connection offers Skip sign in. Home remains available with a sign-in banner, recommendations and moods. | Explicit anonymous/account capability states; an unavailable account feature must not block unrelated playback. |
| Search | Source scopes YouTube / Library / Addons; results have All / Songs / Videos / Albums / Artists categories. | Search results retain source and media kind; cancellation, continuation and identity remain explicit. |
| Version distinction | “Daft Punk Get Lucky” returned album, radio edit, cover and instrumental entries separately. A “Big Buck Bunny” music search returned loosely related music. | Titles alone are insufficient matching evidence. Catalog search success does not establish the intended recording. |
| Initial play | Selecting the album version of Get Lucky produced a playing row and mini-player. Expanded player showed duration 6:08 and time 0:06; later the queue showed 3:45. | Keep visible state coherent across row, mini-player, full player and queue. These observations do not measure time to real sound. |
| Queue and automatic continuation | Queue separates Now playing and AutoPlay. Around the World (Radio Edit) was the recommended next item. Manual Next changed the current item to it, with duration 4:00, and exposed Happy as the next recommendation. | Preserve explicit current occurrence and the distinction between requested queue and generated continuation. A manual Next observation is not an end-of-track auto-advance test. |
| Seek / pause | Clicking the timeline changed the displayed time to 2:38. Pause held near 2:45 and the control changed to Play. | Test seek acknowledgements and saved pause intent, not only optimistic slider state. |
| Song actions | Menu exposed quality, convert to video, radio, Play next, Add to queue, Download, Remove from cache, album/artist, Song Info and sleep timer. | Explicit downloads and disposable cache are distinct. The download action was not executed. |
| Audio → video | Convert to video replaced cover art with an in-player video frame and a fullscreen control. The title changed from the radio-edit label to Around the World; paused display was around 2:46. | This demonstrates embedded presentation, not verified timeline equivalence or single audible ownership. Muses must retain its own stricter timeline and handoff contract. |
| Video → audio | Convert to audio restored radio-edit art/title and paused time 2:45. Back returned to search with the paused mini-player. | Keep one session, explicit return behavior, browsing context and pause intent. |
| Sources | Source page showed JioSaavn disabled with a wrong-version warning, YouTube Music always on, Add an addon, and a WebDAV section. No addon was configured. | Source capability and recording identity must be explicit. Do not silently substitute a plausible same-title recording. |
| Quality labels | Settings showed preferred Wi-Fi quality Lossless, but Sources explicitly said no enabled source could provide lossless. | A selected preference is not actual delivered quality. Muses must display actual format/source separately. |

One bounded raw screenshot is retained at [embedded video paused](../evidence/reference/bitchord-1.9.1-embedded-video-paused.png), 1,680,773 bytes, SHA-256 `1cc12a680cb57e24c88a021f24f0670736944d073f103de68d8ffa771f85db50`. Android Studio saved it to the Desktop; the exact newly created file was moved into this evidence directory. No personal screenshot was touched.

## Limits

The emulator was silent by configuration. No audibility, output gap, bit-perfect, DSP quality, long-run stability, actual media client/protocol, authenticated library writes, offline cold start, multiplayer synchronization or Android-specific integration was proven. Advanced settings scrolling was not successfully inspected; no claim is made about their runtime behavior. The remaining F01–F22 scope comes from the approved plan and independent Muses contracts, not an assertion that every BitChord feature was exercised.

The task IDE project, AVD registration, APK, emulator data, server processes and screenshot helper residues require the separate ownership-checked cleanup receipt. Closing an IDE window alone does not establish that its recent-project or system residues are gone.
