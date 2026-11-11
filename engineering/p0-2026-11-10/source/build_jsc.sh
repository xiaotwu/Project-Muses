#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source
export TMPDIR="$SCRATCH/tmp"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/clang-module-cache"
QJS="$SCRATCH/quickjs-2026-06-04"
clang -O2 -fobjc-arc -Wno-deprecated-declarations -Wno-incompatible-pointer-types -DP0_IOS -I"$QJS" -c "$SOURCE/NativeHost.m" -o "$SCRATCH/build/NativeHost-shared.o"
clang -O2 -fobjc-arc -Wno-deprecated-declarations -Wno-incompatible-pointer-types "$SOURCE/NativeJSCHost.m" "$SCRATCH/build/NativeHost-shared.o" "$SCRATCH/build/quickjs.o" "$SCRATCH/build/dtoa.o" "$SCRATCH/build/libregexp.o" "$SCRATCH/build/libunicode.o" "$SCRATCH/build/cutils.o" -framework Foundation -framework JavaScriptCore -o "$SCRATCH/build/source-proof-jsc"
