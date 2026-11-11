#!/usr/bin/env python3
"""Invoke via frozen run_guarded.py --allocation source; no external network."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import threading
import time

HERE=Path(__file__).resolve().parent
SCRATCH=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport')
CAP=200*1024*1024
BODY=bytes((i*31+7)%256 for i in range(262144))
COUNTS={}

def budget():
    allocated=sum(p.lstat().st_blocks*512 for p in SCRATCH.rglob('*')) if SCRATCH.exists() else 0
    assert allocated < CAP-16*1024*1024
    assert shutil.disk_usage(SCRATCH.parent).free > 40*1024**3
    return allocated

class Server(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        name=self.path.split('?',1)[0]
        COUNTS[name]=COUNTS.get(name,0)+1
        if name=='/slow': time.sleep(3)
        range_header=self.headers.get('Range','')
        if not range_header.startswith('bytes='):
            self.send_error(400);return
        start,end=map(int,range_header[6:].split('-'))
        end=min(end,len(BODY)-1)
        if name=='/forbidden' or (name=='/late-forbidden' and start>0) or (name=='/header-check' and self.headers.get('DNT')!='?1'):
            self.send_response(403);self.send_header('Content-Length','0');self.end_headers();return
        if name=='/ignore':
            self.send_response(200);self.send_header('Content-Length',str(len(BODY)));self.end_headers()
            try:self.wfile.write(BODY)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        total=17*1024**2 if name=='/oversize' else len(BODY)
        claimed=start+1 if name=='/wrong-range' else start
        self.send_response(206)
        self.send_header('Content-Range',f'bytes {claimed}-{end}/{total}')
        self.send_header('Content-Length',str(end-start+1))
        self.send_header('Content-Type','application/octet-stream')
        self.send_header('ETag','"changed"' if name=='/changed' and start>0 else '"fixture-v1"')
        self.end_headers()
        try:
            body=BODY[start:end+1]
            if name=='/short':body=body[:1000]
            for offset in range(0,len(body),4096):
                self.wfile.write(body[offset:offset+4096]);self.wfile.flush()
                time.sleep(.001)
        except (BrokenPipeError,ConnectionResetError):pass

def run(argv,log):
    budget()
    with log.open('w') as output:
        result=subprocess.run(list(map(str,argv)),stdout=output,stderr=subprocess.STDOUT,timeout=45)
    if result.returncode:
        print(log.read_text()[-9000:]);raise SystemExit(result.returncode)

if __name__=='__main__':
    SCRATCH.mkdir(exist_ok=True)
    trial=SCRATCH/time.strftime('%Y%m%d-%H%M%S');trial.mkdir()
    initial=budget()
    run(['clang','-fobjc-arc','-O1','-gline-tables-only','-Wno-deprecated-declarations','-DMT_TESTING',
         HERE/'NativeTransport.m',HERE/'LocalTests.m','-framework','Foundation','-o',trial/'transport-tests'],trial/'build.log')
    server=ThreadingHTTPServer(('127.0.0.1',0),Server);server.daemon_threads=True
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        run([trial/'transport-tests',f'http://127.0.0.1:{server.server_port}',trial],trial/'tests.jsonl')
    finally:
        server.shutdown();server.server_close()
        (trial/'requests.json').write_text(json.dumps(COUNTS,indent=2)+'\n')
    actual=(trial/'complete.bin').read_bytes();assert actual==BODY
    assert not (trial/'must-not-complete.bin').exists()
    assert (trial/'must-not-complete.bin.partial').stat().st_size==65536
    (trial/'receipt.json').write_text(json.dumps({'fixture_sha256':hashlib.sha256(BODY).hexdigest(),
        'complete_sha256':hashlib.sha256(actual).hexdigest(),'fixture_bytes':len(BODY),
        'scratch_cap_bytes':CAP,'initial_allocated_bytes':initial,'final_allocated_bytes':budget(),
        'free_bytes':shutil.disk_usage(SCRATCH).free,
        'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.is_file()}},indent=2)+'\n')
    print(trial)
    print((trial/'tests.jsonl').read_text())
