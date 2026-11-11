#!/usr/bin/env python3
"""One bounded public-source run, retaining sanitized events and hashes only."""
from pathlib import Path
import hashlib,json,subprocess,threading,time
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01');OWNED=ROOT/'audio/macos-streaming'
BUILD=Path((OWNED/'current-build.txt').read_text().strip())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((BUILD/'success.json').read_text());inputs=json.loads((BUILD/'input-manifest.json').read_text())
assert sha(BUILD/'stream-public')==build['binary_sha256']['public']
assert all(sha(Path(p))==h for p,h in build['source_sha256'].items())
for copy in inputs['copies']:assert sha(BUILD/copy['destination'])==copy['sha256']
OUT=OWNED/('public-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()));OUT.mkdir()
raw={'out':bytearray(),'err':bytearray()};overflow=threading.Event()
def collect(pipe,key):
 while True:
  data=pipe.read(4096)
  if not data:break
  if len(raw[key])+len(data)>1024*1024:overflow.set();break
  raw[key].extend(data)
started=time.monotonic();peak=0;reason=None
process=subprocess.Popen([str(BUILD/'stream-public'),'public',str(BUILD/'probe.bundle.js')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
workers=[threading.Thread(target=collect,args=(process.stdout,'out')),threading.Thread(target=collect,args=(process.stderr,'err'))]
for worker in workers:worker.start()
while process.poll() is None:
 used=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
 if used:peak=max(peak,int(used)*1024)
 if peak>256*1024**2 or time.monotonic()-started>90 or overflow.is_set():
  reason='rss' if peak>256*1024**2 else 'log_limit' if overflow.is_set() else 'deadline';process.terminate();break
 time.sleep(.1)
try:code=process.wait(timeout=3)
except subprocess.TimeoutExpired:process.kill();code=process.wait()
for worker in workers:worker.join(timeout=2)
def sanitize(value):
 if isinstance(value,dict):return {k:sanitize(v) for k,v in value.items() if not any(part in k.lower() for part in ('url','visitor','profile','token','cookie','authorization','header','path','filename'))}
 if isinstance(value,list):return [sanitize(v) for v in value[:64]]
 if isinstance(value,str):
  if len(value)>256 or any(part in value.lower() for part in ('http:','https:','googlevideo.com','signature=')):return '[redacted]'
 return value
rows=[];non_json=0
for line in raw['out'].decode(errors='replace').splitlines():
 try:event=json.loads(line)
 except ValueError:non_json+=1;continue
 if isinstance(event,dict):rows.append(sanitize(event))
assert len(rows)<=512
result={'exit_code':code,'stop_reason':reason,'elapsed_seconds':time.monotonic()-started,'sampled_peak_rss_bytes':peak,
        'rss_observation_limit_bytes':256*1024**2,'rss_is_hard_allocator_limit':False,
        'binary_sha256':sha(BUILD/'stream-public'),'bundle_sha256':sha(BUILD/'probe.bundle.js'),
        'build_manifest_sha256':sha(BUILD/'success.json'),'events':rows,'non_json_stdout_redacted':non_json,
        'stdout_sha256':hashlib.sha256(raw['out']).hexdigest(),'stderr_sha256':hashlib.sha256(raw['err']).hexdigest(),
        'stdout_bytes':len(raw['out']),'stderr_bytes':len(raw['err']),'audio_muted':True,'speaker_first_sound_measured':False}
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
(OUT/'manifest.json').write_text(json.dumps({'source_sha256':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},'result_sha256':sha(OUT/'result.json')},indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('events',)}))
for event in rows:
 if event.get('gate') in ('stream_session','stream_input','stream_descriptor_handoff','stream_cleanup','streaming_proof'):print(json.dumps(event))
print(OUT)
raise SystemExit(code if reason is None else 125)
