#!/usr/bin/env python3
"""Guarded local-only AVIO integration. Copies are already hash/provenance checked."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import hashlib,json,shutil,subprocess,threading,time
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport')
INPUT=ROOT/'decoder-inputs'
class Server(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path not in ['/tone-a.m4a','/tone-b.webm']:self.send_error(404);return
        data=(INPUT/'fixtures'/self.path[1:]).read_bytes()
        header=self.headers.get('Range','')
        if not header.startswith('bytes='):self.send_error(400);return
        begin,end=map(int,header[6:].split('-'));end=min(end,len(data)-1)
        self.send_response(206);self.send_header('Content-Range',f'bytes {begin}-{end}/{len(data)}')
        self.send_header('Content-Length',str(end-begin+1));self.send_header('ETag','"'+hashlib.sha256(data).hexdigest()+'"');self.end_headers()
        try:self.wfile.write(data[begin:end+1])
        except (BrokenPipeError,ConnectionResetError):pass
def run(argv,path):
    with path.open('w')as log:result=subprocess.run(list(map(str,argv)),stdout=log,stderr=subprocess.STDOUT,timeout=45)
    if result.returncode:print(path.read_text()[-8000:]);raise SystemExit(result.returncode)
if __name__=='__main__':
    assert sum(p.lstat().st_blocks*512 for p in ROOT.rglob('*'))<184*1024**2
    assert shutil.disk_usage(ROOT).free>40*1024**3
    folder=ROOT/('avio-'+time.strftime('%Y%m%d-%H%M%S'));folder.mkdir()
    run(['clang','-fobjc-arc','-O2','-Wno-deprecated-declarations','-DMT_TESTING','-c',HERE/'NativeTransport.m','-o',folder/'transport.o'],folder/'native-build.log')
    run(['clang++','-std=c++17','-O2','-I'+str(INPUT/'include'),HERE/'AVIOTests.cpp',folder/'transport.o',
         *[INPUT/'lib'/(name+'.a')for name in ['libavformat','libavcodec','libavutil','libswresample']],'-framework','Foundation','-o',folder/'avio-tests'],folder/'avio-build.log')
    server=ThreadingHTTPServer(('127.0.0.1',0),Server);server.daemon_threads=True;threading.Thread(target=server.serve_forever,daemon=True).start()
    try:run([folder/'avio-tests',f'http://127.0.0.1:{server.server_port}',INPUT/'fixtures'],folder/'results.jsonl')
    finally:server.shutdown();server.server_close()
    (folder/'receipt.json').write_text(json.dumps({'input_provenance_sha256':hashlib.sha256((INPUT/'provenance.json').read_bytes()).hexdigest(),
        'sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in HERE.iterdir()if p.is_file()},
        'allocated_bytes':sum(p.lstat().st_blocks*512 for p in ROOT.rglob('*')),'free_bytes':shutil.disk_usage(ROOT).free},indent=2)+'\n')
    print(folder);print((folder/'results.jsonl').read_text())
