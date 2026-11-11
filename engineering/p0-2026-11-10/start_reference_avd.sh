#!/bin/bash
set -euo pipefail
scratch=/Users/xiaotwu/.muses/tmp/p0-20261110-01/android
sdk=/Users/xiaotwu/Library/Android/sdk
export ANDROID_SDK_ROOT="$sdk"
export ANDROID_HOME="$sdk"
export ANDROID_USER_HOME="$scratch/user"
export ANDROID_EMULATOR_HOME="$scratch/emulator"
export ANDROID_AVD_HOME="$scratch/avd"
export ANDROID_SDK_HOME="$scratch"
export ADB_SERVER_SOCKET=tcp:localhost:5038
export TMPDIR="$scratch/tmp/"
mkdir -p "$ANDROID_USER_HOME" "$ANDROID_EMULATOR_HOME" "$ANDROID_AVD_HOME" "$TMPDIR"
exec "$sdk/emulator/emulator" -avd Muses_P0_BitChord_191 -port 5580 -no-snapshot -no-boot-anim -no-audio -camera-back none -camera-front none -memory 2048 -cores 2 -partition-size 1024 -gpu host -no-metrics -crash-report-mode never -qt-hide-window -grpc 8554 -grpc-use-token >"$scratch/emulator-grpc.log" 2>&1
