---
layout: default
title: Windows Privacy
---

# Muses Privacy Policy & Security Principles

Muses is built from the ground up to respect your privacy and provide an uncompromised, local-first listening experience.

## Core Commitments

1. **Zero Telemetry & Zero Analytics**
   - Muses collects no analytics, telemetry, diagnostic logs, or usage metrics.
   - We do not operate remote telemetry servers, tracking pixels, or heartbeat pingers.
   - No crash reports or personal data are sent to any remote servers without explicit user initiation.

2. **Local-First Architecture**
   - Your listening history, playlists, queue, tracks, bookmarks, notes, equalizer presets, and automation rules reside strictly on your device in a local SQLite database.
   - Default database path (see `SqliteStore.DefaultPath`):
     - Windows: `%APPDATA%\Muses\muses-youtube-native.sqlite`
     - macOS (dev checkout): `~/Library/Application Support/MusesEuterpe/muses-youtube-native.sqlite`
   - Cache data (lyrics, artwork, stream URL cache) stays under the same app-data root.

3. **Secure Credential Storage**
   - Account tokens (optional Google OAuth) are stored in the platform's native secure storage (Windows Credential Locker / DPAPI; macOS Keychain when available).
   - Plaintext passwords or raw session tokens are never logged or stored in plain JSON/text files under app data.

4. **Isolated Web Home Helper**
   - Web Home helper runs as a separate process (`MusesWebHomeHelper`) with its own volatile ephemeral session directory under the OS temp root (`muses-web-home-helper/…`).
   - Session cookies live only in that permission-restricted jar and are deleted when the helper exits.
   - The Avalonia UI process does not scrape YouTube Home or hold Web Home cookies.
   - Web Home is **off by default** and requires explicit consent (`PrefKey.WebHomeEnabled` / consent version).

5. **Direct Media Resolving**
   - Streaming URLs are resolved locally via bundled open-source `yt-dlp` directly to YouTube media servers.
   - Stream traffic flows between your machine and YouTube CDNs without a Muses-operated proxy.

6. **Automatic Updates**
   - When the user checks for updates, Muses contacts GitHub's public API (`api.github.com/repos/xiaotwu/Muses-Euterpe/releases`) only.
   - No personal identifiers, machine IDs, or unique device fingerprints are sent.

## Data Removal

Delete application data by removing the app-data folder:
- Windows: `%APPDATA%\Muses` (and `%LOCALAPPDATA%\Muses` if present)
- macOS (dev): `~/Library/Application Support/MusesEuterpe`

Settings → General includes **Clear Cache** (artwork + Home feed cache) and **Reset Data** (deletes the SQLite library, caches, signs out of Credential Manager, then quits). Reset is irreversible.
