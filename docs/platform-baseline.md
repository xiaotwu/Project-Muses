---
layout: default
title: Platform baseline
---

# Polyhymnia is the product baseline

The macOS repository defines the Muses product, data semantics and interaction direction. iOS and Windows adapt that direction to their native platforms. They are platform projects, not forks with independent product definitions.

This baseline is based on the macOS source and guidance at the family migration, including the current G1 champagne-gold palette. The published 0.5.6 artifacts predate subsequent development changes; the website's existing screenshots illustrate their capture-time UI rather than guaranteeing the latest working-tree appearance.

## Product and data

- YouTube-backed music, playlists, music videos and followed podcasts; artwork-led discovery.
- One playback facade, one library and one coherent queue. Keep collection context, explicit Up Next and history distinct.
- Preserve likes, pins, metadata, playlist order, bookmarks, listening history and podcast progress during upgrades and any Windows rebuild.
- Do not bring back folder scanning, local-file import, M3U, Radio or a Music Inbox navigation entry.
- Albums and artists need stable provider IDs, not display-name merging. Unavailable features must not be advertised as implemented.

## Interaction and appearance

- Search, Home and New, followed by library and playlists; Settings remains directly accessible.
- Native platform navigation: macOS toolbar/sidebar, iPhone/iPad adaptive navigation, Windows caption/sidebar and native system integration.
- Persistent browsing player, integrated queue, expressive cover/vinyl Now Playing, on-demand video and available lyrics. Hide the browsing player in Settings and full Now Playing while keeping playback state coherent.
- Champagne-gold navigation/headings, graphite transport, warm-white surfaces, bounded native glass, accessible contrast and native control typography. Artwork and reading regions remain clear.
- macOS F3 typography is the direction: Georgia/Songti for editorial titles and lyrics, Avenir Next/PingFang/Hiragino for song information, native system fonts for chrome. Ports use suitable licensed/system fallbacks.
- Keyboard/focus, screen-reader names, reduced motion/transparency, and phone/tablet/window-size adaptation are acceptance requirements.

## Platform constraints

| Area | Polyhymnia | Erato | Euterpe |
| --- | --- | --- | --- |
| Playback implementation | yt-dlp → native AVPlayer/AVAudioEngine | Public: visible official player; Native: separate experimental composition | yt-dlp → mpv IPC |
| Desktop/phone integration | Menu bar, macOS media controls | Native iPhone/iPad behavior; Public pauses in background | Windows SMTC/tray, native caption, Mica/Acrylic |
| Source and status authority | Current macOS source and runtime evidence | Current iOS source and its channel-specific evidence | Current Windows source and runtime evidence |
| Release boundary | Signed, notarized Mac artifacts | Preserve Public/Native signing and provisioning restrictions | Windows packaging/signing; no package yet published |

A shared product baseline does not make all playback engines interchangeable. Reusing a macOS resolver in the iOS Public composition changes that channel's boundary and requires an explicit product decision. Do not infer Windows support from successful macOS tests.

## Windows rebuilding rule

The Windows implementation may be replaced rather than preserving its old layout. Preserve user data and useful validated domain behavior; rebuild UI and platform integration against Polyhymnia. First establish a data preservation fixture and playback/queue acceptance cases, then rebuild shell/navigation, collections, player/queue/Now Playing, discovery and Windows integrations. Verify each milestone on Windows 11 before claiming parity or distributing an installer.

This repository migration establishes ownership and direction. It does not certify complete iOS/Windows feature or visual parity and does not constitute a completed Windows rebuild.

The owner selected a full Windows rebuild on 2026-09-30 and will start it in a separate project. This migration does not begin that rebuild.
