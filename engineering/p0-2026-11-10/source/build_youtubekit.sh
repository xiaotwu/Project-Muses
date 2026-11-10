#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source
export TMPDIR="$SCRATCH/tmp"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/youtubekit-module-cache"
export SWIFTPM_MODULECACHE_OVERRIDE="$SCRATCH/youtubekit-module-cache"
export SWIFT_MODULECACHE_PATH="$SCRATCH/youtubekit-module-cache"
REV=7f75a2299dc329c0b7855afb25d47663a02855cb
if [ ! -f "$SCRATCH/downloads/YouTubeKit-$REV.tar.gz" ]; then curl --fail --location --max-time 60 "https://codeload.github.com/alexeichhorn/YouTubeKit/tar.gz/$REV" -o "$SCRATCH/downloads/YouTubeKit-$REV.tar.gz"; fi
ACTUAL=$(shasum -a 256 "$SCRATCH/downloads/YouTubeKit-$REV.tar.gz" | cut -d ' ' -f 1)
[ "$ACTUAL" = 8272e8acb6f8db7b01f1e3fbb4e0bbee11af0200aa0768091407282a6644e92a ] || { echo 'YouTubeKit archive checksum mismatch'; exit 1; }
if [ ! -d "$SCRATCH/YouTubeKit-$REV" ]; then tar -xzf "$SCRATCH/downloads/YouTubeKit-$REV.tar.gz" -C "$SCRATCH"; fi
mkdir -p "$SCRATCH/youtubekit-probe/Sources/Probe"
cp "$SOURCE/YouTubeKitProbe.swift" "$SCRATCH/youtubekit-probe/Sources/Probe/Probe.swift"
python3 "$SOURCE/prepare_youtubekit.py"
swift build --package-path "$SCRATCH/youtubekit-probe" --scratch-path "$SCRATCH/youtubekit-build" --cache-path "$SCRATCH/youtubekit-cache" --config-path "$SCRATCH/youtubekit-config" --security-path "$SCRATCH/youtubekit-security" --disable-sandbox --disable-keychain --disable-netrc --disable-index-store -j 2
python3 - "$SOURCE/YouTubeKitProbe.swift" <<'PY'
import hashlib,json,sys
from pathlib import Path
s=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source')
p=s/'youtubekit-build/out/Products/Debug/Probe'
(s/'results/youtubekit-build-success.json').write_text(json.dumps({'source_sha256':hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(p.read_bytes()).hexdigest()},indent=2)+'\n')
PY
shasum -a 256 "$SCRATCH/downloads/YouTubeKit-$REV.tar.gz"
