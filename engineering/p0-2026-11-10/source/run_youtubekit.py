#!/usr/bin/env python3
"""One alternate proof, 256 MiB observed RSS and 75 s external CLI budget."""
import datetime,hashlib,json,os,subprocess,time,sys
from pathlib import Path
s=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source')
binary=s/'youtubekit-build/out/Products/Debug/Probe'
build=json.loads((s/'results/youtubekit-build-success.json').read_text())
if build['source_sha256']!=hashlib.sha256((Path(__file__).parent/'YouTubeKitProbe.swift').read_bytes()).hexdigest() or build['binary_sha256']!=hashlib.sha256(binary.read_bytes()).hexdigest():raise SystemExit('stale build refused')
started=time.monotonic();peak=0;reason=None
diagnostic=sys.argv[1:]==['--diagnostic-512']
if sys.argv[1:] and not diagnostic:raise SystemExit('unknown option')
limit=(512 if diagnostic else 256)*1024*1024
seconds=60 if diagnostic else 75
environment=dict(os.environ,TMPDIR=str(s/'tmp'),OS_ACTIVITY_MODE='disable')
p=subprocess.Popen([str(binary)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment)
while p.poll() is None:
    rss=subprocess.run(['ps','-o','rss=','-p',str(p.pid)],capture_output=True,text=True).stdout.strip()
    if rss:peak=max(peak,int(rss)*1024)
    if peak>limit:reason='external process RSS ceiling'
    if time.monotonic()-started>seconds:reason='external deadline'
    if reason:p.terminate();break
    time.sleep(.05)
out,err=p.communicate(timeout=5)
if len(out)>65536 or b'googlevideo.com' in out or b'visitorData' in out:raise SystemExit('receipt refused')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
record={'library':'YouTubeKit','commit':'7f75a2299dc329c0b7855afb25d47663a02855cb','exit_code':p.returncode,'stop_reason':reason,'elapsed_seconds':time.monotonic()-started,'process_peak_rss_bytes':peak,'stdout':out.decode(),'stderr_bytes':len(err),'host_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'external_deadline_seconds':seconds,'rss_limit_bytes':limit,'explicit_diagnostic_exception':diagnostic,'production_budget_changed':False}
path=s/'results'/f'{stamp}-youtubekit-{512 if diagnostic else 256}.json';path.write_text(json.dumps(record,indent=2)+'\n');print(out.decode(),end='');print('YouTubeKit receipt:',path);print('Guard:',reason or 'completed','peak RSS:',peak);raise SystemExit(p.returncode or 0)
