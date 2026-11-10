#!/bin/sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SCRATCH=/Users/xiaotwu/.muses/tmp/p0-20261110-01/source
export TMPDIR="$SCRATCH/tmp"
export CLANG_MODULE_CACHE_PATH="$SCRATCH/clang-module-cache-ios"
OUT="$SCRATCH/iphoneos"
QJS="$SCRATCH/quickjs-2026-06-04"
SDK=$(xcrun --sdk iphoneos --show-sdk-path)
mkdir -p "$OUT/MusesP0Source.app"
for UNIT in quickjs dtoa libregexp libunicode cutils; do
  if [ ! -f "$OUT/$UNIT.o" ] || [ "$QJS/$UNIT.c" -nt "$OUT/$UNIT.o" ]; then
    xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 -O2 -DNDEBUG -DCONFIG_VERSION='"2026-06-04"' -D_GNU_SOURCE -I"$QJS" -c "$QJS/$UNIT.c" -o "$OUT/$UNIT.o"
  fi
done
for UNIT in NativeHost iOSMain; do
  xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 -O2 -fobjc-arc -Wno-deprecated-declarations -Wno-incompatible-pointer-types -DP0_IOS -I"$QJS" -I"$SOURCE/../audio" -c "$SOURCE/$UNIT.m" -o "$OUT/$UNIT.o"
done
AUDIO=/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/iphoneos
xcrun --sdk iphoneos clang -arch arm64 -isysroot "$SDK" -miphoneos-version-min=17.0 "$OUT/NativeHost.o" "$OUT/iOSMain.o" "$OUT/quickjs.o" "$OUT/dtoa.o" "$OUT/libregexp.o" "$OUT/libunicode.o" "$OUT/cutils.o" "$AUDIO/audio-probe.o" "$AUDIO/miniaudio-backend.o" "$AUDIO/libavformat/libavformat.a" "$AUDIO/libavcodec/libavcodec.a" "$AUDIO/libswresample/libswresample.a" "$AUDIO/libavutil/libavutil.a" -framework UIKit -framework Foundation -framework AVFAudio -framework AudioToolbox -framework CoreAudio -framework MediaPlayer -framework Security -lc++ -lz -lbz2 -liconv -o "$OUT/MusesP0Source.app/MusesP0Source"
cp "$SOURCE/iOS-Info.plist" "$OUT/MusesP0Source.app/Info.plist"
cp "$SCRATCH/build/probe.bundle.js" "$OUT/MusesP0Source.app/probe.bundle.js"
for SLOT in first next; do
  if [ -f "$OUT/calibration-$SLOT.m4a" ]; then cp "$OUT/calibration-$SLOT.m4a" "$OUT/MusesP0Source.app/calibration-$SLOT.m4a"; fi
done
plutil -lint "$OUT/MusesP0Source.app/Info.plist"
echo "Unsigned iOS app prepared; root owns signing, device deployment and foreground verification."
