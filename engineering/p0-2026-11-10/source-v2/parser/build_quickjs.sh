#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser
QJS=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/quickjs-2026-06-04
DEPS=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/deps/node_modules
export TMPDIR="$SCRATCH/tmp"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/module-cache"
"$DEPS/@esbuild/darwin-arm64/bin/esbuild" "$SOURCE/extract.js" --bundle --format=iife --platform=neutral --target=es2022 --alias:p0-upstream="$DEPS/youtubei.js/dist/src" --alias:meriyah="$DEPS/meriyah/dist/meriyah.mjs" --outfile="$SCRATCH/build/extract.bundle.js"
for name in quickjs dtoa libregexp libunicode cutils; do
  if [ ! -f "$SCRATCH/build/qjs-$name.o" ]; then
    cc -std=gnu11 -O2 -g0 -fwrapv -DCONFIG_VERSION='"2026-06-04"' -I"$QJS" -c "$QJS/$name.c" -o "$SCRATCH/build/qjs-$name.o"
  fi
done
cc -std=gnu11 -O2 -g0 -I"$QJS" "$SOURCE/quickjs_phase.c" "$SCRATCH/build/qjs-quickjs.o" "$SCRATCH/build/qjs-dtoa.o" "$SCRATCH/build/qjs-libregexp.o" "$SCRATCH/build/qjs-libunicode.o" "$SCRATCH/build/qjs-cutils.o" -lm -o "$SCRATCH/build/quickjs-phase"
