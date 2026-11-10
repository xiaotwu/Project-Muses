#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser
export TMPDIR="$SCRATCH/tmp"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/module-cache"
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
TS="$SCRATCH/tree-sitter"
JS="$SCRATCH/tree-sitter-javascript"
OUT="$SCRATCH/build/iphoneos"
mkdir -p "$OUT"
clang -target arm64-apple-ios17.0 -isysroot "$SDK" -std=gnu11 -O2 -g0 -I"$TS/lib/include" -I"$TS/lib/src" -c "$TS/lib/src/lib.c" -o "$OUT/tree-sitter.o"
clang -target arm64-apple-ios17.0 -isysroot "$SDK" -std=gnu11 -O2 -g0 -I"$JS/src" -c "$JS/src/parser.c" -o "$OUT/javascript.o"
clang -target arm64-apple-ios17.0 -isysroot "$SDK" -std=gnu11 -O2 -g0 -I"$JS/src" -c "$JS/src/scanner.c" -o "$OUT/scanner.o"
clang -target arm64-apple-ios17.0 -isysroot "$SDK" -std=gnu11 -O2 -g0 -I"$TS/lib/include" -c "$SOURCE/p0_parser.c" -o "$OUT/p0_parser.o"
xcrun libtool -static -o "$OUT/libp0parser.a" "$OUT/p0_parser.o" "$OUT/tree-sitter.o" "$OUT/javascript.o" "$OUT/scanner.o"
