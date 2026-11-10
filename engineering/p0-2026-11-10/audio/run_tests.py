#!/usr/bin/env python3
"""Run bounded synthetic tests and loopback HTTP range/cancellation proof.

Use run_guarded.py --allocation audio. Default is silent: native output receives
zeros. Passing --audible is an explicit opt-in and must be coordinated first.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
import time

ROOT = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio')
REQUESTS = []

class Media(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/slow':
            REQUESTS.append({'path': self.path, 'delayed_headers_ms': 3000})
            time.sleep(3)
        if self.path not in ['/tone-a.m4a', '/tone-b.webm']:
            try:
                self.send_error(404)
            except (BrokenPipeError, ConnectionResetError):
                pass
            return
        data = (ROOT / 'fixtures' / self.path[1:]).read_bytes()
        assert len(data) < 1024 * 1024
        header = self.headers.get('Range', '')
        start, end = 0, len(data) - 1
        if header.startswith('bytes='):
            values = header[6:].split('-', 1)
            start = int(values[0] or 0)
            end = int(values[1]) if values[1] else end
        end = min(end, len(data) - 1)
        if start > end:
            self.send_error(416)
            return
        REQUESTS.append({'path': self.path, 'range_start': start, 'range_end': end})
        self.send_response(206 if header else 200)
        self.send_header('Content-Type', 'audio/mp4' if self.path.endswith('.m4a') else 'audio/webm')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Accept-Ranges', 'bytes')
        if header:
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
        self.end_headers()
        try:
            for cursor in range(start, end + 1, 4096):
                self.wfile.write(data[cursor:min(cursor+4096, end+1)])
                self.wfile.flush()
                time.sleep(0.004)
        except (BrokenPipeError, ConnectionResetError):
            pass

def run(args, path):
    with path.open('w') as output:
        result = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT, timeout=45)
    print(path.name + ': exit ' + str(result.returncode), flush=True)
    print(path.read_text(), end='', flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--audible', action='store_true')
    options = parser.parse_args()
    evidence = ROOT / 'results' / time.strftime('%Y%m%d-%H%M%S')
    evidence.mkdir(parents=True, exist_ok=False)
    probe = ROOT / 'macosx/audio-probe'
    fixtures = [str(ROOT / 'fixtures/tone-a.m4a'), str(ROOT / 'fixtures/tone-b.webm')]
    run([str(probe), 'tests', *fixtures], evidence / 'local.jsonl')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Media)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_address[1])
    try:
        run([str(probe), 'tests', base+'/tone-a.m4a', base+'/tone-b.webm', base+'/slow'], evidence / 'stream.jsonl')
    finally:
        server.shutdown()
        server.server_close()
        (evidence / 'http-requests.json').write_text(json.dumps(REQUESTS, indent=2) + '\n')
    run([str(probe), 'audible' if options.audible else 'device', *fixtures], evidence / 'device.jsonl')
    run([str(probe), 'session', *fixtures], evidence / 'late-next.jsonl')
