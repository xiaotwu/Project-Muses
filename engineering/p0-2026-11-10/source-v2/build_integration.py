#!/usr/bin/env python3
"""Versioned, hash-checked adaptation of the initial native host proof."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

SOURCE = Path(__file__).resolve().parent
BASE = SOURCE.parent / 'source'
SCRATCH = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration')
QJS = SCRATCH.parent / 'quickjs-2026-06-04'
BUILD = SCRATCH / 'build'
BUILD.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, TMPDIR=str(SCRATCH / 'tmp'), CLANG_MODULE_CACHE_PATH=str(BUILD / 'module-cache'),
           NODE_PATH=str(SCRATCH / 'deps/node_modules'))
source = (BASE / 'NativeHost.m').read_bytes()
assert hashlib.sha256(source).hexdigest() == 'bd1fc0329bc8008f12bde2f5753661555c66d782addb1bcf66644bd6874ce7fc'
text = source.decode()
old_main = '#ifndef P0_IOS\nint main(int argc,char **argv){ if(argc<2)return 64;return RunProof(@(argv[1]),argc>2?@(argv[2]):@"catalog"); }\n#endif'
assert old_main in text
text = text.replace(old_main, '')
def change(old, new):
    global text
    assert text.count(old) == 1, old
    text = text.replace(old, new)
change('#include <time.h>', '#include <time.h>\n' + (SOURCE / 'NativeControl.inc').read_text() + '\n' + (SOURCE / 'NativeInput.inc').read_text())
change('JS_Eval(inner,utf8.bytes,utf8.length,"isolated-player.js",JS_EVAL_TYPE_GLOBAL)', 'P0EvaluateData(inner,utf8,"isolated-player.js",JS_EVAL_TYPE_GLOBAL)')
change('JS_Eval(context,source.bytes,source.length,"p0.bundle.js",JS_EVAL_TYPE_GLOBAL)', 'P0EvaluateData(context,source,"p0.bundle.js",JS_EVAL_TYPE_GLOBAL)')
change('NSData *source=[NSData dataWithContentsOfFile:bundlePath];', 'NSData *source=[NSData dataWithContentsOfFile:bundlePath];\n        Output(JSONString(@{@"gate":@"source_bundle_read",@"outcome":source?@"pass":@"fail",@"bytes":@(source.length),@"sha256":source?V2SHA(source.bytes,source.length):@""}));')
change('static uint64_t maxBody = 16 * 1024 * 1024;', 'static uint64_t maxBody = 4 * 1024 * 1024;')
change('return Now() > deadline;', 'return Now() > deadline || V2ShouldStop();')
change('return Now()>*(double *)opaque;', 'return Now()>*(double *)opaque || V2ShouldStop();')
change('while(!finished && Now()<deadline)', 'while(!finished && Now()<deadline && !V2ShouldStop())')
change('while((jobs=JS_ExecutePendingJob(runtime,&jobContext))>0){}', 'while(!finished && !V2ShouldStop() && executedJobs++<128 && (jobs=JS_ExecutePendingJob(runtime,&jobContext))>0){}')
change('JSContext *jobContext; int jobs;', 'JSContext *jobContext; int jobs=0, executedJobs=0;')
change('if([timer[@"due"] doubleValue]<=Now())', 'if(!finished && !V2ShouldStop() && [timer[@"due"] doubleValue]<=Now())')
change('if (ms<0) [bridge.timers removeObjectForKey:@(n)];', 'if(ms>=0 && bridge.timers.count>=128 && !bridge.timers[@(n)])return JS_ThrowRangeError(ctx,"native timer limit");\n    if (ms<0) [bridge.timers removeObjectForKey:@(n)];')
change('if (bridge.requests.count>=4)', 'if (bridge.requests.count>=4 || bridge.requestCount>=32 || V2ShouldStop())')
change('if (body.length + data.length > maxBody)', 'if (body.length + data.length > maxBody || _receivedBytes + data.length > 16*1024*1024)')
change('JSRuntime *isolated=JS_NewRuntime();JS_SetMemoryLimit', 'JSRuntime *isolated=JS_NewRuntime();if(!isolated)return nil;JS_SetMemoryLimit')
change('JSContext *inner=JS_NewContext(isolated);', 'JSContext *inner=JS_NewContext(isolated);if(!inner){JS_FreeRuntime(isolated);return nil;}')
change('runtime=JS_NewRuntime2(&Allocator,NULL);', 'runtime=JS_NewRuntime2(&Allocator,NULL);if(!runtime){[bridge.session invalidateAndCancel];bridge=nil;return 1;}')
change('context=JS_NewContext(runtime);', 'context=JS_NewContext(runtime);if(!context){JS_FreeRuntime(runtime);runtime=NULL;[bridge.session invalidateAndCancel];bridge=nil;return 1;}')
old_error = source.decode().split('static void Error(const char *stage) {', 1)[1].split('int RunProof(', 1)[0]
change('static void Error(const char *stage) {' + old_error,
       'static void Error(const char *stage) {\n'
       '    JSValue exception=JS_GetException(context);JS_FreeValue(context,exception);\n'
       '    Output(JSONString(@{@"gate":@(stage),@"outcome":@"fail",@"category":@"runtime_exception",@"stop_reason":V2StopReason()}));\n'
       '}\n')
change('int RunProof(NSString *bundlePath, NSString *mode) {',
       (SOURCE / 'NativeHooks.inc').read_text() + '\nint RunProof(NSString *bundlePath, NSString *mode) {')
change('NSUInteger heapMiB=[NSProcessInfo.processInfo.environment[@"P0_HEAP_MIB"] integerValue]==128 ? 128 : 64;', 'NSUInteger heapMiB=64;')
change('Register("nativeStoreMedia",NativeStoreMedia,3);', 'Register("nativeDescriptor",V2ReceiveDescriptor,1);')
change('JS_SetPropertyStr(context,global,"PROBE_MODE",JSString(context,mode));',
       'JS_SetPropertyStr(context,global,"PROBE_MODE",JSString(context,mode));JS_SetPropertyStr(context,global,"SOURCE_CLIENT",JSString(context,V2Client));JS_SetPropertyStr(context,global,"SOURCE_CODEC",JSString(context,V2Codec));')
change('for(NSDictionary *event in events) {', 'for(NSDictionary *originalEvent in events) {\n                    NSDictionary *event=V2FilterEvent(originalEvent);if(!event){finished=YES;resultCode=1;break;}')
change('NSDictionary *event=V2FilterEvent(originalEvent);', 'if(finished)break;if(V2ShouldStop()){finished=YES;resultCode=1;break;} NSDictionary *event=V2FilterEvent(originalEvent);')
# Metadata cannot accidentally start a media request through the old buffered bridge.
change(' || [h isEqual:@"googlevideo.com"] || [h hasSuffix:@".googlevideo.com"]', '')
generated = BUILD / 'NativeHost.v2.m'
generated.write_text(text)
bundle = BUILD / 'probe.bundle.js'
commands = [[str(SCRATCH / 'deps/node_modules/.bin/esbuild'), str(SOURCE / 'probe.mjs'),
             '--bundle', '--platform=neutral', '--format=iife', '--target=es2022', '--keep-names', '--outfile=' + str(bundle)]]
for unit in ['quickjs', 'dtoa', 'libregexp', 'libunicode', 'cutils']:
    obj = BUILD / (unit + '.o')
    commands.append(['clang', '-O2', '-DNDEBUG', '-DCONFIG_VERSION="2026-06-04"', '-D_GNU_SOURCE', '-I' + str(QJS), '-c', str(QJS / (unit + '.c')), '-o', str(obj)])
binary = BUILD / 'source-v2'
parser_scratch = SCRATCH.parent / 'v2-parser'
parser_objects = [parser_scratch / 'build' / (name + '.o') for name in ['tree-sitter', 'javascript', 'scanner']]
decoder_inputs = SCRATCH.parent / 'v2-transport/decoder-inputs'
decoder_libraries = [decoder_inputs / 'lib' / (name + '.a') for name in ['libavformat', 'libavcodec', 'libswresample', 'libavutil']]
commands.append(['clang++', '-std=c++17', '-O2', '-Wno-deprecated-declarations', '-I' + str(decoder_inputs / 'include'),
                 '-c', str(SOURCE / 'transport/DecodeProbe.cpp'), '-o', str(BUILD / 'DecodeProbe.o')])
commands.append(['clang', '-std=gnu11', '-O2', '-I' + str(parser_scratch / 'tree-sitter/lib/include'),
                 '-c', str(SOURCE / 'parser/p0_parser.c'), '-o', str(BUILD / 'p0_parser.o')])
commands.append(['clang', '-O2', '-fobjc-arc', '-Wno-deprecated-declarations', '-Wno-incompatible-pointer-types', '-I' + str(QJS),
                 '-I' + str(SOURCE), str(generated), str(SOURCE / 'transport/NativeTransport.m'), *[str(BUILD / (x + '.o')) for x in ['quickjs', 'dtoa', 'libregexp', 'libunicode', 'cutils']],
                 str(BUILD / 'p0_parser.o'), *map(str, parser_objects),
                 str(BUILD / 'DecodeProbe.o'), *map(str, decoder_libraries), '-lc++',
                 '-framework', 'Foundation', '-o', str(binary)])
files = [BASE / 'NativeHost.m', BASE / 'shims.js', SOURCE / 'probe.mjs', SOURCE / 'availability.mjs', SOURCE / 'client-profiles.mjs',
         SOURCE / 'NativeHooks.inc', SOURCE / 'NativeControl.inc', SOURCE / 'NativeInput.inc', SOURCE / 'build_integration.py', SOURCE / 'transport/NativeTransport.m', SOURCE / 'transport/muses_transport.h',
         SOURCE / 'parser/p0_parser.c', SOURCE / 'parser/p0_parser.h', *parser_objects,
         SOURCE / 'transport/DecodeProbe.cpp', SOURCE / 'transport/muses_decode_probe.h', *decoder_libraries]
files.extend(sorted(QJS.glob('*.h')))
files.extend(QJS / (unit + '.c') for unit in ['quickjs', 'dtoa', 'libregexp', 'libunicode', 'cutils'])
source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
for command in commands:
    subprocess.run(command, env=env, check=True)
assert source_hashes == {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}, 'source changed during build; no success receipt'
receipt = {'source_sha256': source_hashes,
           'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(), 'bundle_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest(),
           'generated_host_sha256': hashlib.sha256(generated.read_bytes()).hexdigest(), 'commands': commands}
(BUILD / 'success.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({'build': 'pass', 'binary_sha256': receipt['binary_sha256'], 'bundle_sha256': receipt['bundle_sha256']}))
