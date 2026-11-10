#!/bin/sh
set -eu
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export TMPDIR="$SCRATCH/tmp"
export npm_config_cache="$SCRATCH/npm-cache"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/clang-module-cache"
mkdir -p "$TMPDIR" "$SCRATCH/deps" "$SCRATCH/downloads" "$SCRATCH/results"
cd "$SCRATCH/deps"
cp "$SOURCE/package.json" "$SOURCE/package-lock.json" .
npm ci --ignore-scripts --no-audit --no-fund
if [ ! -f "$SCRATCH/downloads/quickjs-2026-06-04.tar.xz" ]; then
  curl --fail --location --max-time 60 https://bellard.org/quickjs/quickjs-2026-06-04.tar.xz -o "$SCRATCH/downloads/quickjs-2026-06-04.tar.xz"
fi
EXPECTED=b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a
ACTUAL=$(shasum -a 256 "$SCRATCH/downloads/quickjs-2026-06-04.tar.xz" | cut -d ' ' -f 1)
[ "$ACTUAL" = "$EXPECTED" ] || { echo 'QuickJS archive checksum mismatch'; exit 1; }
if [ ! -d "$SCRATCH/quickjs-2026-06-04" ]; then
  tar -xf "$SCRATCH/downloads/quickjs-2026-06-04.tar.xz" -C "$SCRATCH"
fi
shasum -a 256 "$SCRATCH/downloads/quickjs-2026-06-04.tar.xz"
node -e 'for(const n of ["youtubei.js","esbuild","web-streams-polyfill","fast-text-encoding"]){ const p=JSON.parse(require("fs").readFileSync(`node_modules/${n}/package.json`)); console.log(n,p.version,p.license) }'
