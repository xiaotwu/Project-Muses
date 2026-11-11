#!/usr/bin/env python3
"""Local drain/lifecycle regressions and independent complete-file PCM reference."""
from pathlib import Path
import argparse,hashlib,http.server,json,re,subprocess,threading,time,urllib.parse
HERE=Path(__file__).resolve().parent;ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-streaming/v2')
BUILD=Path((ROOT/'current-build.txt').read_text().strip());KIT=ROOT/'kit'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((BUILD/'success.json').read_text())
assert all(sha(BUILD/name)==digest for name,digest in build['binary_sha256'].items())
assert all(sha(Path(p))==h for p,h in build['source_sha256'].items())
fixtures={'aac':KIT/'fixtures/aac-44100-40s.m4a','opus':KIT/'fixtures/opus-48000-40s.webm',
 'aac-short':KIT/'fixtures/aac-short.m4a','aac-tiny':KIT/'fixtures/aac-tiny.m4a','opus-short':KIT/'fixtures/opus-short.webm',
 'offset':KIT/'fixtures/aac-positive-offset.m4a','aac-unknown':ROOT/'extra-fixtures/aac-unknown-duration.mka',
 'offset-mka':ROOT/'timeline-fixtures/aac-positive.mka','normalized-mp4':ROOT/'timeline-fixtures/aac-normalized.m4a'}
requests=[];lock=threading.Lock()
class Server(http.server.ThreadingHTTPServer):daemon_threads=True
class Handler(http.server.BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*unused):pass
 def do_GET(self):
  parsed=urllib.parse.urlsplit(self.path);name=parsed.path.strip('/');mode=urllib.parse.parse_qs(parsed.query).get('mode',['normal'])[0]
  source=fixtures.get(name)
  if source is None:self.send_error(404);return
  length=source.stat().st_size;match=re.fullmatch(r'bytes=(\d+)-(\d+)',self.headers.get('Range',''))
  if not match:self.send_error(400);return
  start,end=map(int,match.groups());end=min(end,length-1)
  with lock:
   assert len(requests)<512
   requests.append({'fixture':name,'mode':mode,'start':start,'end':end,'length':length,'monotonic_ns':time.monotonic_ns()})
  if start>length-1:self.send_error(416);return
  self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{length}');self.send_header('Content-Length',str(end-start+1))
  self.send_header('Content-Type','application/octet-stream');self.send_header('ETag','"p0-v2-fixed"');self.send_header('Connection','close');self.end_headers()
  broken=mode=='disconnect' or (mode=='second-failure' and start>=32768)
  remaining=(end-start+1)//2 if broken else end-start+1
  try:
   with source.open('rb') as media:
    media.seek(start)
    while remaining:
     chunk=media.read(min(16384,remaining));self.wfile.write(chunk);self.wfile.flush();remaining-=len(chunk);time.sleep(.003)
  except (BrokenPipeError,ConnectionResetError):pass
  self.close_connection=True
parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args()
cases=[('aac-full','eof','aac-short',None),('aac-swr-tail','eof','aac-unknown',None),('tiny-terminal','terminal-seek-reject','aac-tiny',None),
 ('opus-full','eof','opus-short',None),('positive-mp4-full','eof','offset',None),('positive-mp4-seek','timeline-seek','offset',1.30),
 ('positive-mka-full','eof','offset-mka',None),('positive-mka-seek','timeline-seek','offset-mka',1.30),('disconnect','disconnect','aac',None),
 ('late-failure','late-failure','aac',None),('full-ring-cancel','full-ring-cancel','aac',None),('active-cancel','active-cancel','opus',None),
 ('aac-tail-seek','tail-seek','aac',39.95),('opus-tail-seek','tail-seek','opus',39.95),('publish-seek','publish-seek','opus',39.95),('late','late','aac',None)]
if args.case:cases=[row for row in cases if row[0]==args.case]
assert cases
OUT=ROOT/('local-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()));OUT.mkdir()
server=Server(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
rows=[]
def run(command,label):
 started=time.monotonic();peak=0;reason=None
 with (OUT/(label+'.stdout.jsonl')).open('wb') as out,(OUT/(label+'.stderr.log')).open('wb') as err:
  process=subprocess.Popen(command,stdout=out,stderr=err)
  while process.poll() is None:
   raw=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
   if raw:peak=max(peak,int(raw)*1024)
   if peak>256*1024**2 or time.monotonic()-started>20:reason='rss' if peak>256*1024**2 else 'deadline';process.terminate();break
   time.sleep(.05)
  try:code=process.wait(timeout=3)
  except subprocess.TimeoutExpired:process.kill();code=process.wait()
 events=[json.loads(line) for line in (OUT/(label+'.stdout.jsonl')).read_text().splitlines() if line.startswith('{')]
 return {'exit_code':code,'stop_reason':reason,'sampled_peak_rss_bytes':peak,'elapsed_seconds':time.monotonic()-started,'events':events}
try:
 for name,mode,fixture,start in cases:
  suffix='?mode=second-failure' if mode=='late-failure' else '?mode=disconnect' if mode=='disconnect' else ''
  command=[str(BUILD/'stream-local'),'local',mode,base+'/'+fixture+suffix,str(fixtures[fixture].stat().st_size)]
  if start is not None:command.append(str(start))
  if mode=='late':command += [base+'/opus',str(fixtures['opus'].stat().st_size)]
  row=run(command,name);row['case']=name;rows.append(row)
  (OUT/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
  assert row['exit_code']==0 and row['stop_reason'] is None,(name,'process failed')
  events=row['events'];drain=next(e for e in events if e.get('gate')=='stream_drain' and e.get('slot')==0)
  if mode in ('eof','terminal-seek-reject','tail-seek','publish-seek','timeline-seek'):
   reference_fixture={'offset':'normalized-mp4','offset-mka':'aac-unknown'}.get(fixture,fixture)
   reference=run([str(BUILD/'reference'),str(fixtures[reference_fixture]),str(start or 0)],name+'-reference');row['reference']=reference;row['reference_fixture']=reference_fixture
   assert reference['exit_code']==0 and reference['stop_reason'] is None
   ref=next(e for e in reference['events'] if e.get('gate')=='offline_reference')
   pcm=next(e for e in events if e.get('gate')=='seek_pcm') if start is not None else drain
   row['complete_pcm_equal']=pcm['produced_frames']==pcm['consumed_frames']==ref['frames'] and pcm['produced_pcm_sha256']==pcm['consumed_pcm_sha256']==ref['pcm_sha256']
   assert row['complete_pcm_equal'],(name,'independent PCM mismatch',pcm,ref)
   if name=='aac-swr-tail':assert drain['swr_drain_frames']>0,'fixture did not exercise SWR tail'
   if name=='opus-full':assert ref['frames']==59731,'pre-skip/discard-padding count differs from source frames'
  if mode=='late-failure':assert next(e for e in events if e.get('gate')=='stream_end')['reason']=='input_failed'
  if mode=='full-ring-cancel':assert next(e for e in events if e.get('gate')=='cancel_join')['elapsed_ms']<1000
  (OUT/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
  print(json.dumps({k:v for k,v in row.items() if k not in ('events','reference')}),flush=True)
finally:
 server.shutdown();server.server_close();(OUT/'requests.json').write_text(json.dumps(requests,indent=2)+'\n')
 (OUT/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
 (OUT/'manifest.json').write_text(json.dumps({'build_success_sha256':sha(BUILD/'success.json'),'runner_sha256':sha(Path(__file__)),
  'fixtures':{k:{'sha256':sha(p),'bytes':p.stat().st_size} for k,p in fixtures.items()},'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file()},'audible':False,'external_network':False},indent=2)+'\n')
 print(OUT,flush=True)
