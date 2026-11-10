#!/usr/bin/env python3
"""Build generic native decoder comparison and run local fixtures only."""
from pathlib import Path
import hashlib,json,subprocess,sys,threading,time
sys.dont_write_bytecode=True
from run_avio import HERE,ROOT,INPUT,Server,ThreadingHTTPServer,run
if __name__=='__main__':
    folder=ROOT/('decoder-probe-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir()
    outputs={}
    for sdk,triple in [('macosx','arm64-apple-macos26.0'),('iphoneos','arm64-apple-ios17.0')]:
        sdkpath=subprocess.check_output(['xcrun','--sdk',sdk,'--show-sdk-path'],text=True).strip()
        dest=ROOT/sdk/'DecodeProbe.o'
        run(['clang++','-std=c++17','-O2','-Wno-deprecated-declarations','-target',triple,'-isysroot',sdkpath,'-I'+str(INPUT/'include'),'-c',HERE/'DecodeProbe.cpp','-o',dest],folder/(sdk+'-build.log'))
        outputs[sdk]={'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'bytes':dest.stat().st_size}
    run(['clang','-fobjc-arc','-O2','-Wno-deprecated-declarations','-DMT_TESTING','-c',HERE/'NativeTransport.m','-o',folder/'transport.o'],folder/'native-build.log')
    run(['clang++','-std=c++17','-O2','-I'+str(INPUT/'include'),HERE/'DecodeProbeTests.cpp',ROOT/'macosx/DecodeProbe.o',folder/'transport.o',
         *[INPUT/'lib'/(n+'.a')for n in ['libavformat','libavcodec','libswresample','libavutil']],'-framework','Foundation','-o',folder/'tests'],folder/'test-build.log')
    server=ThreadingHTTPServer(('127.0.0.1',0),Server);server.daemon_threads=True;threading.Thread(target=server.serve_forever,daemon=True).start()
    try:run([folder/'tests',f'http://127.0.0.1:{server.server_port}',INPUT/'fixtures'],folder/'results.jsonl')
    finally:server.shutdown();server.server_close()
    (folder/'objects.json').write_text(json.dumps(outputs,indent=2)+'\n')
    print(json.dumps(outputs));print(folder);print((folder/'results.jsonl').read_text())
