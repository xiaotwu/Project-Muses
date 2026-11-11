#!/usr/bin/env python3
"""Controlled loopback transport; no external requests or audible output."""
from pathlib import Path
import hashlib,http.server,json,os,re,subprocess,threading,time
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01');OWNED=ROOT/'audio/macos-streaming'
BUILD=Path((OWNED/'current-build.txt').read_text().strip())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((BUILD/'success.json').read_text())
assert sha(BUILD/'stream-local')==build['binary_sha256']['local']
assert all(sha(Path(p))==h for p,h in build['source_sha256'].items())
OUT=OWNED/('local-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()));OUT.mkdir()
fixtures={'aac':BUILD/'fixtures/aac-44100-40s.m4a','opus':BUILD/'fixtures/opus-48000-40s.webm'}
requests=[];lock=threading.Lock()
class Server(http.server.ThreadingHTTPServer):daemon_threads=True
class Handler(http.server.BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*unused):pass
 def do_GET(self):
  mode=self.path.strip('/');source=fixtures['opus' if mode=='opus' else 'aac'];length=source.stat().st_size
  match=re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers.get('Range',''))
  if not match:self.send_error(400);return
  start,end=map(int,match.groups());end=min(end,length-1)
  with lock:requests.append({'mode':mode,'start':start,'end':end,'length':length,'monotonic_ns':time.monotonic_ns()})
  if start>length-1:self.send_error(416);return
  ignore=mode=='ignore';response_length=length if ignore else end-start+1
  self.send_response(200 if ignore else 206)
  if not ignore:self.send_header('Content-Range',f'bytes {start}-{end}/{length}')
  self.send_header('Content-Length',str(response_length));self.send_header('Content-Type','application/octet-stream');self.send_header('ETag','"p0-fixed-fixture"');self.send_header('Connection','close');self.end_headers()
  if mode=='stall':time.sleep(7)
  amount=response_length//2 if mode=='disconnect' else response_length
  try:
   with source.open('rb') as media:
    media.seek(0 if ignore else start)
    while amount:
     data=media.read(min(16384,amount));self.wfile.write(data);self.wfile.flush();amount-=len(data);time.sleep(.02)
  except (BrokenPipeError,ConnectionResetError):pass
  self.close_connection=True
server=Server(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'
cases=[('aac','aac','aac'),('opus','opus','opus'),('late','late','aac'),('seek-aac','seek','aac'),('seek-opus','seek','opus'),('disconnect','disconnect','disconnect'),('ignore-range','ignore','ignore'),('cancel','cancel','stall')]
rows=[]
try:
 for name,mode,path in cases:
  size=fixtures['opus' if path=='opus' else 'aac'].stat().st_size
  command=[str(BUILD/'stream-local'),'local',mode,base+'/'+path,str(size)]
  if mode=='late':command += [base+'/opus',str(fixtures['opus'].stat().st_size)]
  started=time.monotonic();peak=0;stop=None
  with (OUT/(name+'.stdout.jsonl')).open('wb') as out,(OUT/(name+'.stderr.log')).open('wb') as err:
   process=subprocess.Popen(command,stdout=out,stderr=err)
   while process.poll() is None:
    observed=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
    if observed:peak=max(peak,int(observed)*1024)
    if peak>256*1024**2 or time.monotonic()-started>15:
     stop='rss' if peak>256*1024**2 else 'deadline';process.terminate();break
    time.sleep(.1)
   try:code=process.wait(timeout=3)
   except subprocess.TimeoutExpired:process.kill();code=process.wait()
  events=[json.loads(line) for line in (OUT/(name+'.stdout.jsonl')).read_text().splitlines() if line.startswith('{')]
  cancelled=next((x for x in events if x.get('gate')=='cancel_join'),None)
  result={'case':name,'exit_code':code,'stop_reason':stop,'sampled_peak_rss_bytes':peak,'elapsed_seconds':time.monotonic()-started,'events':events}
  if cancelled:result['cancel_under_1000ms']=cancelled['elapsed_ms']<1000
  rows.append(result);print(json.dumps({k:v for k,v in result.items() if k!='events'}),flush=True)
  (OUT/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
  if code or stop or (cancelled and not result['cancel_under_1000ms']):raise RuntimeError('local case failed: '+name)
finally:
 server.shutdown();server.server_close()
 (OUT/'requests.json').write_text(json.dumps(requests,indent=2)+'\n')
 manifest={'source_sha256':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},'build_manifest_sha256':sha(BUILD/'success.json'),
           'binary_sha256':sha(BUILD/'stream-local'),'fixtures':{k:{'sha256':sha(v),'bytes':v.stat().st_size} for k,v in fixtures.items()},
           'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file()},'external_network':False,'audio_muted':True}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(OUT,flush=True)
