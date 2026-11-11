#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser
export TMPDIR="$SCRATCH/tmp"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/module-cache"
clang -O2 -g0 -fobjc-arc -framework Foundation -framework JavaScriptCore "$SOURCE/jsc_reference.m" -o "$SCRATCH/build/jsc-reference"
