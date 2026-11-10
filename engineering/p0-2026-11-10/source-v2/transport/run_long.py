#!/usr/bin/env python3
"""Generate owned40s fixtures with developer ffmpeg; no distributable GPL linkage."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import hashlib,json,shutil,subprocess,threading,time
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport')
INPUT=ROOT/'decoder-inputs'
FIXTURES=ROOT/'long-fixtures'
NAMES=['aac-44100-40s.m4a','opus-48000-40s.webm']
class Server(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        name=self.path[1:]
        if name not in NAMES:self.send_error(404);return
        data=(FIXTURES/name).read_bytes();header=self.headers.get('Range','')
        if not header.startswith('bytes='):self.send_error(400);return
        start,end=map(int,header[6:].split('-'));end=min(end,len(data)-1)
        self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}');self.send_header('Content-Length',str(end-start+1));self.send_header('ETag','"fixed"');self.end_headers()
        try:self.wfile.write(data[start:end+1])
        except (BrokenPipeError,ConnectionResetError):pass
def run(argv,path):
    with path.open('w')as log:result=subprocess.run(list(map(str,argv)),stdout=log,stderr=subprocess.STDOUT,timeout=90)
    if result.returncode:print(path.read_text()[-8000:]);raise SystemExit(result.returncode)
if __name__=='__main__':
    assert sum(p.lstat().st_blocks*512 for p in ROOT.rglob('*'))<180*1024**2
    assert shutil.disk_usage(ROOT).free>40*1024**3
    folder=ROOT/('long-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir();FIXTURES.mkdir(exist_ok=True)
    run(['/opt/homebrew/bin/ffmpeg','-version'],folder/'development-generator.txt')
    commands=[]
    for name,samplerate,freq,codec in [(NAMES[0],44100,440,'aac'),(NAMES[1],48000,660,'libopus')]:
        if not (FIXTURES/name).exists():
            argv=['/opt/homebrew/bin/ffmpeg','-v','error','-nostdin','-n','-f','lavfi','-i',f'sine=frequency={freq}:sample_rate={samplerate}:duration=40','-ac','2','-c:a',codec,'-b:a','96k']
            if codec=='aac':argv+=['-movflags','+faststart']
            argv+=[str(FIXTURES/name)];commands.append(argv);run(argv,folder/(name+'-generation.log'))
    run(['clang','-fobjc-arc','-O2','-Wno-deprecated-declarations','-DMT_TESTING','-c',HERE/'NativeTransport.m','-o',folder/'transport.o'],folder/'native-build.log')
    run(['clang++','-std=c++17','-O2',HERE/'LongDecodeTests.cpp',ROOT/'macosx/DecodeProbe.o',folder/'transport.o',
         *[INPUT/'lib'/(n+'.a')for n in ['libavformat','libavcodec','libswresample','libavutil']],'-framework','Foundation','-o',folder/'tests'],folder/'build.log')
    server=ThreadingHTTPServer(('127.0.0.1',0),Server);server.daemon_threads=True;threading.Thread(target=server.serve_forever,daemon=True).start()
    try:run([folder/'tests',f'http://127.0.0.1:{server.server_port}',FIXTURES],folder/'results.jsonl')
    finally:server.shutdown();server.server_close()
    (folder/'manifest.json').write_text(json.dumps({'generation_commands':commands,'fixtures':{n:{'bytes':(FIXTURES/n).stat().st_size,'sha256':hashlib.sha256((FIXTURES/n).read_bytes()).hexdigest()}for n in NAMES},
        'production_decoder_object_sha256':hashlib.sha256((ROOT/'macosx/DecodeProbe.o').read_bytes()).hexdigest()},indent=2)+'\n')
    print(folder);print((folder/'results.jsonl').read_text())
