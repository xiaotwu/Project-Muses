#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser
export TMPDIR="$SCRATCH/tmp"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/module-cache"
TS="$SCRATCH/tree-sitter"
JS="$SCRATCH/tree-sitter-javascript"
if [ ! -f "$SCRATCH/build/tree-sitter.o" ]; then cc -std=gnu11 -O2 -g0 -I"$TS/lib/include" -I"$TS/lib/src" -c "$TS/lib/src/lib.c" -o "$SCRATCH/build/tree-sitter.o"; fi
if [ ! -f "$SCRATCH/build/javascript.o" ]; then cc -std=gnu11 -O2 -g0 -I"$JS/src" -c "$JS/src/parser.c" -o "$SCRATCH/build/javascript.o"; fi
if [ ! -f "$SCRATCH/build/scanner.o" ]; then cc -std=gnu11 -O2 -g0 -I"$JS/src" -c "$JS/src/scanner.c" -o "$SCRATCH/build/scanner.o"; fi
cc -std=gnu11 -O2 -g0 -Wall -Wextra -I"$TS/lib/include" -c "$SOURCE/p0_parser.c" -o "$SCRATCH/build/p0_parser.o"
cc -std=gnu11 -O2 -g0 "$SOURCE/parser_cli.c" "$SCRATCH/build/p0_parser.o" "$SCRATCH/build/tree-sitter.o" "$SCRATCH/build/javascript.o" "$SCRATCH/build/scanner.o" -lpthread -o "$SCRATCH/build/parser-proof"
cc -std=gnu11 -O2 -g0 -I"$TS/lib/include" "$SOURCE/parser_tests.c" "$SCRATCH/build/p0_parser.o" "$SCRATCH/build/tree-sitter.o" "$SCRATCH/build/javascript.o" "$SCRATCH/build/scanner.o" -lpthread -o "$SCRATCH/build/parser-tests"
