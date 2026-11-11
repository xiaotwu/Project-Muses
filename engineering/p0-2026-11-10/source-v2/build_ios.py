#!/usr/bin/env python3
"""Build the isolated v2 iOS candidate from a verified desktop host snapshot.

No signing, device operations, release builds, or global dependency changes.
"""
from pathlib import Path
import hashlib
import json
import os
import plistlib
import subprocess

SOURCE = Path(__file__).resolve().parent
SCRATCH = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration')
BUILD = SCRATCH / 'iphoneos'
APP = BUILD / 'MusesP0Source.app'
QJS = SCRATCH.parent / 'quickjs-2026-06-04'
AUDIO = SCRATCH.parent.parent / 'audio/iphoneos'
PARSER = SCRATCH.parent / 'v2-parser/build/iphoneos/libp0parser.a'
desktop = json.loads((SCRATCH / 'build/success.json').read_text())
for path, expected in desktop['source_sha256'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, 'stale desktop source snapshot'
host = SCRATCH / 'build/NativeHost.v2.m'
assert hashlib.sha256(host.read_bytes()).hexdigest() == desktop['generated_host_sha256']
assert hashlib.sha256(PARSER.read_bytes()).hexdigest() == 'a2a112b997e569bca8a6fffe85f48f1170b503cbc7b9996a9b076022d3cd6459'
assert hashlib.sha256((AUDIO / 'audio-probe.o').read_bytes()).hexdigest() == '324b4b09fc763d3bc5733b334670522d5d0a8160706cf580a7898221ee872c12'
assert hashlib.sha256((AUDIO / 'miniaudio-backend.o').read_bytes()).hexdigest() == '6e346b04baf3b7519e3d4e56a87679e8742b24404698417ac629c9fc3c4ac285'
APP.mkdir(parents=True, exist_ok=True)
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
common = ['clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, '-O2']
env = dict(os.environ, TMPDIR=str(SCRATCH / 'tmp'), CLANG_MODULE_CACHE_PATH=str(BUILD / 'module-cache'))
commands = []
objects = []
for unit in ['quickjs', 'dtoa', 'libregexp', 'libunicode', 'cutils']:
    obj = BUILD / (unit + '.o')
    commands.append(common + ['-DNDEBUG', '-DCONFIG_VERSION="2026-06-04"', '-D_GNU_SOURCE',
                             '-I'+str(QJS), '-c', str(QJS / (unit + '.c')), '-o', str(obj)])
    objects.append(obj)
for name, source in [('NativeHost', host), ('NativeTransport', SOURCE / 'transport/NativeTransport.m'),
                     ('iOSMain', SOURCE / 'ios/iOSMain.m')]:
    obj = BUILD / (name + '.o')
    commands.append(common + ['-fobjc-arc', '-Wno-deprecated-declarations', '-Wno-incompatible-pointer-types',
        '-DP0_IOS', '-I'+str(QJS), '-I'+str(SOURCE), '-I'+str(SOURCE.parent / 'audio'), '-c', str(source), '-o', str(obj)])
    objects.append(obj)
dependencies = [AUDIO / 'audio-probe.o', AUDIO / 'miniaudio-backend.o', PARSER]
dependencies.extend(AUDIO / name / (name + '.a') for name in ['libavformat', 'libavcodec', 'libswresample', 'libavutil'])
binary = APP / 'MusesP0Source'
commands.append(common + list(map(str, objects + dependencies)) + ['-framework', 'UIKit', '-framework', 'Foundation',
    '-framework', 'AVFAudio', '-framework', 'AudioToolbox', '-framework', 'CoreAudio', '-framework', 'MediaPlayer',
    '-framework', 'Security', '-lc++', '-lz', '-lbz2', '-liconv', '-o', str(binary)])
files = [SOURCE / 'build_ios.py', SOURCE / 'ios/iOSMain.m', SOURCE / 'ios/RunPolicy.h', SOURCE.parent / 'source/iOS-Info.plist',
         SOURCE.parent / 'audio/p0_audio.h', host, *dependencies]
hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
for command in commands:
    subprocess.run(command, env=env, check=True)
assert hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}, 'inputs changed during build'
for path, expected in desktop['source_sha256'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, 'desktop inputs changed during iOS build'
info = plistlib.loads((SOURCE.parent / 'source/iOS-Info.plist').read_bytes())
info['CFBundleVersion'] = '6'
info['UIApplicationSceneManifest']['UISceneConfigurations']['UIWindowSceneSessionRoleApplication'][0]['UISceneDelegateClassName'] = 'P0V2SceneDelegate'
(APP / 'Info.plist').write_bytes(plistlib.dumps(info))
bundle = (SCRATCH / 'build/probe.bundle.js').read_bytes()
assert hashlib.sha256(bundle).hexdigest() == desktop['bundle_sha256']
(APP / 'probe.bundle.js').write_bytes(bundle)
subprocess.run(['plutil', '-lint', str(APP / 'Info.plist')], check=True)
record = {'kind': 'unsigned_ios_candidate_6', 'source_sha256': hashes, 'desktop_inputs': desktop['source_sha256'],
          'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'bundle_sha256': desktop['bundle_sha256'], 'commands': commands,
          'signing': False, 'device_runtime_verified': False}
(BUILD / 'build-success.json').write_text(json.dumps(record, indent=2)+'\n')
print(json.dumps({'build': 'pass', 'kind': record['kind'], 'binary_sha256': record['binary_sha256']}))
