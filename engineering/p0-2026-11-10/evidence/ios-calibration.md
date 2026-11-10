# Physical iPhone calibration — evidence and limits

The probe ran on a paired iPhone 15 Pro, iOS 27.2.1 (24B156), under an existing development wildcard profile. No portal registration, personal library, user account, browser cookie, app group or Keychain data was used. Its unique identifier is `org.muses.p0.sourceprobe`. The device identifier and provisioning profile remain private scratch, outside Git.

The native host owns `AVAudioSession.playback` with `mixWithOthers`. Its independent FFmpeg/miniaudio bridge uses one output clock and 0.12 app gain. Two task-generated 95-second AAC sine files (440 Hz / 660 Hz) are bundled. Thirty seconds after audio starts, a new QuickJS catalog job performs real network requests; the next bundled input is then prepared and crossfaded. Audio stops after 90 seconds. The media source is deliberately synthetic: **this is not a provider-media playback proof**.

Fixture SHA-256: first `6be992306a703c3f081b3e9b499481f4f5ec8a43ac4d14a7ef0ca547aa62a4e0`, next `eb09ed379c49df24a97db7019a15840b934918365cf11f9a3934381d52d61cce`. Each was generated using the existing Homebrew `ffmpeg` with `sine=frequency=440|660:sample_rate=48000:duration=95`, AAC 96k, `+faststart`. The executable is only a fixture generator, not a linked runtime dependency.

## Attempts are retained separately

| Attempt | Result |
| --- | --- |
| Candidate 1 | Signed and installed; replaced before launch by candidate 2. No runtime claim. |
| Candidate 2 | Launch crashed before controller setup. Sanitized crash shows `___UIApplicationEvaluateRuntimeIssueForNoSceneLifecycleAdoption_block_invoke` / SIGTRAP. A plain diagnostic launch exited without a valid trace. Added a scene manifest and `UIWindowScene`/SceneDelegate; the failure remains in evidence. |
| Candidate 3, run 3 | 90.057 s native run, one transition, zero recorded PCM underflows, and increasing next-input/nonzero-output counters after the fade. Catalog requests failed immediately with `network_-1009`. User initially reported no sound, then corrected that sound was present and the volume had been low. Captured lifecycle labels were active. |
| Candidate 3, run 4 | After the user confirmed network permission/availability, search returned 20 results, continuation 20, music 28 sections; catalog peak JS allocation 10,607,318 bytes, process max RSS 71,106,560 bytes. Native run 90.048 s, one transition and zero recorded underflows. User reported full locked listening, changed tone and automatic stop. Logs captured only a brief background interval and otherwise active labels; sustained lock is not independently corroborated. |
| Candidate 3, run 5 | A controlled follow-up requested side-button lock and phone face down; no device query occurred during the 90 s playback window. Search/continuation/music passed (20/20/28), process max RSS 70,500,352 bytes. Native run 90.084 s, one transition and zero recorded underflows. The same manual lifecycle label remained active. This isolates mid-run diagnostic queries as unnecessary for the observed discrepancy; it does not establish its cause. |

Candidate 3 unsigned binary SHA-256 `bf92cf2e1d49c97b77e830cc4f034ebbec70d10d76f2c084e69907d9f5a88b3a`; signed binary `d50209ad92e13a0d0f3c5ac05a54470a30633030cb88aa740f0a864d6cedbd26`. The same installed bytes were used for runs 3–5. Signing receipts, raw application traces, sanitized crash and computed deltas are in [ios/](ios/).

## What the evidence establishes

The physical device executed native decoding/output, prepared a second decoder after output began, produced nonzero output after the fade while the first input's consumption stayed fixed, ran bounded QuickJS + URLSession catalog requests concurrently, and stopped output at approximately 90 seconds. User feedback establishes audibility for the tested calibration. Output callbacks alone are not the hearing evidence.

The observation code used a manually maintained `active`/`background` label and did not record `sceneWillResignActive`, `UIApplication.applicationState` or `UIScene.activationState`. This is insufficient to distinguish foreground-inactive states from active/background conditions. The discrepancy with the user's locked-listening report is **an unresolved evidence/instrumentation issue**, not proof that the user did not lock the phone or that background audio failed. An improved state collector and a corroborated interval are required before closing that gate. Do not merge the human report and an unrelated foreground request into a false locked-next pass.

No result here proves real provider-media continuity, background fresh-media resolution, route/interruption recovery, long-run battery behavior, download management, system termination survival or release signing/notarization. Source failures remain separate in the source report. The task app is retained, with output stopped, for the unfinished P0 investigation; its local test trace/cache must be included in the eventual isolated-app cleanup.
