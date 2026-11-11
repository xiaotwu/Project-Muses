#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source
export TMPDIR="$SCRATCH/tmp"
export npm_config_cache="$SCRATCH/npm-cache"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/clang-module-cache"
mkdir -p "$SCRATCH/build"
NODE_PATH="$SCRATCH/deps/node_modules" "$SCRATCH/deps/node_modules/.bin/esbuild" "$SOURCE/probe.js" --bundle --platform=neutral --format=iife --target=es2022 --keep-names --outfile="$SCRATCH/build/probe.bundle.js"
QJS="$SCRATCH/quickjs-2026-06-04"
for UNIT in quickjs dtoa libregexp libunicode cutils; do
  if [ ! -f "$SCRATCH/build/$UNIT.o" ]; then
    clang -O2 -DNDEBUG -DCONFIG_VERSION='"2026-06-04"' -D_GNU_SOURCE -I"$QJS" -c "$QJS/$UNIT.c" -o "$SCRATCH/build/$UNIT.o"
  fi
done
clang -O2 -fobjc-arc -Wno-deprecated-declarations -Wno-incompatible-pointer-types -I"$QJS" "$SOURCE/NativeHost.m" "$SCRATCH/build/quickjs.o" "$SCRATCH/build/dtoa.o" "$SCRATCH/build/libregexp.o" "$SCRATCH/build/libunicode.o" "$SCRATCH/build/cutils.o" -framework Foundation -o "$SCRATCH/build/source-proof"
