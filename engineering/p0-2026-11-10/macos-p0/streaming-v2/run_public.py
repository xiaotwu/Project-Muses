#!/usr/bin/env python3
"""One muted public Opus prefix + near-tail seek, with retained-file PCM reference."""
from pathlib import Path
import hashlib,json,subprocess,threading,time
HERE=Path(__file__).resolve().parent;ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-streaming/v2')
BUILD=Path((ROOT/'current-build.txt').read_text().strip());KIT=ROOT/'kit';TARGET=634.5
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((BUILD/'success.json').read_text());plan=json.loads((HERE/'inputs-plan.json').read_text())
assert all(sha(BUILD/name)==digest for name,digest in build['binary_sha256'].items())
assert all(sha(Path(p))==h for p,h in build['source_sha256'].items())
reference=Path(plan['public_reference']['path']);assert sha(reference)==plan['public_reference']['sha256']
OUT=ROOT/('public-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()));OUT.mkdir()
def sanitize(v):
 if isinstance(v,dict):return {k:sanitize(x) for k,x in v.items() if not any(s in k.lower() for s in ('url','visitor','profile','token','cookie','authorization','header','path','filename'))}
 if isinstance(v,list):return [sanitize(x) for x in v[:64]]
 if isinstance(v,str) and (len(v)>256 or any(s in v.lower() for s in ('https:','http:','googlevideo.com','signature='))):return '[redacted]'
 return v
def run(command,deadline):
 raw={'out':bytearray(),'err':bytearray()};overflow=threading.Event();start=time.monotonic();peak=0;reason=None
 process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
 def collect(pipe,key):
  while True:
   data=pipe.read(4096)
   if not data:return
   if len(raw[key])+len(data)>1024*1024:overflow.set();return
   raw[key].extend(data)
 workers=[threading.Thread(target=collect,args=(process.stdout,'out')),threading.Thread(target=collect,args=(process.stderr,'err'))]
 for worker in workers:worker.start()
 while process.poll() is None:
  rss=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
  if rss:peak=max(peak,int(rss)*1024)
  if peak>256*1024**2 or time.monotonic()-start>deadline or overflow.is_set():
   reason='rss' if peak>256*1024**2 else 'log_limit' if overflow.is_set() else 'deadline';process.terminate();break
  time.sleep(.05)
 try:code=process.wait(timeout=3)
 except subprocess.TimeoutExpired:process.kill();code=process.wait()
 for worker in workers:worker.join(timeout=2)
 events=[];nonJSON=0
 for line in raw['out'].decode(errors='replace').splitlines():
  try:event=json.loads(line)
  except ValueError:nonJSON+=1;continue
  if isinstance(event,dict):events.append(sanitize(event))
 assert len(events)<=512
 return {'exit_code':code,'stop_reason':reason,'elapsed_seconds':time.monotonic()-start,'sampled_peak_rss_bytes':peak,'events':events,
  'stdout_sha256':hashlib.sha256(raw['out']).hexdigest(),'stderr_sha256':hashlib.sha256(raw['err']).hexdigest(),
  'stdout_bytes':len(raw['out']),'stderr_bytes':len(raw['err']),'non_json_stdout_redacted':nonJSON}
result={'target_seconds':TARGET,'reference_file_sha256':sha(reference),'reference_file_bytes':reference.stat().st_size,
 'binary_sha256':sha(BUILD/'stream-public'),'build_success_sha256':sha(BUILD/'success.json'),'bundle_sha256':sha(KIT/'probe.bundle.js'),
 'audible':False,'speaker_first_sound_measured':False,'full_track_continuous_playback':False,'playback_scope':'prefix then seek-to-tail',
 'rss_observation_limit_bytes':256*1024**2,'rss_is_hard_allocator_limit':False}
try:
 result['reference']=run([str(BUILD/'reference'),str(reference),str(TARGET)],20)
 assert result['reference']['exit_code']==0 and result['reference']['stop_reason'] is None,'offline reference failed'
 result['public']=run([str(BUILD/'stream-public'),'public-opus',str(KIT/'probe.bundle.js'),str(TARGET)],90)
 actual=result['public'];assert actual['exit_code']==0 and actual['stop_reason'] is None,'public process failed'
 events=actual['events'];decoded=next(e for e in events if e.get('gate')=='stream_drain');source=next(e for e in events if e.get('gate')=='source_descriptor')
 assert source['codec']=='opus' and source['video_id']=='aqz-KE-bpKQ' and source['content_length']==reference.stat().st_size,'public representation changed'
 assert decoded['codec']=='opus' and decoded['phase']=='ended','actual decoder did not finish Opus'
 pcm=next(e for e in events if e.get('gate')=='seek_pcm');ref=next(e for e in result['reference']['events'] if e.get('gate')=='offline_reference')
 result['tail_pcm_equal']=pcm['produced_frames']==pcm['consumed_frames']==ref['frames'] and pcm['produced_pcm_sha256']==pcm['consumed_pcm_sha256']==ref['pcm_sha256']
 assert result['tail_pcm_equal'],'streamed public seek tail differs from retained representation reference'
 result['outcome']='pass'
except Exception as error:
 result['outcome']='fail';result['failure']=str(error)[:180]
finally:
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 (OUT/'manifest.json').write_text(json.dumps({'runner_sha256':sha(Path(__file__)),'result_sha256':sha(OUT/'result.json'),'input_plan_sha256':sha(HERE/'inputs-plan.json')},indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('reference','public')}))
 for name in ('reference','public'):
  if name in result:print(json.dumps({name:{k:v for k,v in result[name].items() if k!='events'}}))
 print(OUT)
raise SystemExit(0 if result.get('outcome')=='pass' else 1)
