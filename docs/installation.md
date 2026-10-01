---
layout: default
title: Installation
---

# Choose your Muses

All platform releases are collected in [Project-Muses Releases](https://github.com/xiaotwu/Project-Muses/releases). Version numbers belong to each platform. A release for iOS does not update your Mac or Windows app.

## macOS — Polyhymnia

Requires **macOS 14 or later**. Download the DMG or ZIP from [Polyhymnia 0.5.6](https://github.com/xiaotwu/Project-Muses/releases/tag/polyhymnia%2Fv0.5.6). Open the DMG and drag **Muses** into **Applications**, or unzip the app into Applications. These published artifacts are signed, notarized and stapled; aggregation does not alter their bytes.

Your library remains available when replacing the application. Start with Home or import a YouTube playlist. Connect Google in Settings → Account if desired. Browser-session Home requires separate consent.

## iOS — Erato

Requires **iOS 18 or later**, with adaptive iPhone/iPad layouts. [Erato 1.0.0 beta 2](https://github.com/xiaotwu/Project-Muses/releases/tag/erato%2Fv1.0.0-beta.2) contains separate Public and experimental Native IPAs. Follow the installation and signing restrictions in its release notes.

The Public IPA has App Store distribution signing for App Store Connect/TestFlight upload; it is not directly installable as an Ad Hoc package. The Native IPA is Ad Hoc and requires a provisioned device or valid re-signing. GitHub publication does not establish Apple review or Google OAuth verification. Public uses a visible YouTube player and pauses when backgrounded; Native background/lock-screen behavior remains experimental. Google account features may require an approved test account.

See [iOS support](ios/), [privacy](ios/privacy.html), [terms](ios/terms.html) and [source/build instructions](https://github.com/xiaotwu/Muses-Erato).

## Windows 11 — Euterpe

No downloadable Windows release is currently published. Microsoft Store and WinGet distribution are also unpublished. Build from [Euterpe source](https://github.com/xiaotwu/Muses-Euterpe) using .NET 10; native playback needs mpv and yt-dlp. Follow the repository's [installation and packaging guide](https://github.com/xiaotwu/Muses-Euterpe/blob/main/INSTALL.md). MSIX packaging requires Windows and the Windows SDK.
