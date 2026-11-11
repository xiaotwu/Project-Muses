#!/usr/bin/env python3
"""Explicit CLI experiment guard; not an iOS memory-budget implementation."""
import datetime, hashlib, json, subprocess, sys, time
from pathlib import Path
s=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source')
mode=sys.argv[1] if len(sys.argv)>1 else 'media'
if mode not in {'media','catalog','background_first','background_next','player_first','player_next'}:raise SystemExit('unknown mode')
started=time.monotonic();peak=0;reason=None
p=subprocess.Popen([str(s/'build/source-proof-jsc'),str(s/'build/probe.bundle.js'),mode],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
while p.poll() is None:
    rss=subprocess.run(['ps','-o','rss=','-p',str(p.pid)],capture_output=True,text=True).stdout.strip()
    if rss:peak=max(peak,int(rss)*1024)
    if peak>256*1024*1024:reason='process RSS ceiling'
    if time.monotonic()-started>95:reason='external deadline'
    if reason:p.terminate();break
    time.sleep(.05)
out,err=p.communicate(timeout=5)
if len(out)>65536 or b'googlevideo.com' in out or b'visitorData' in out:raise SystemExit('receipt refused')
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
record={'runtime':'JavaScriptCore CLI experiment','mode':mode,'exit_code':p.returncode,'stop_reason':reason,'process_peak_rss_bytes':peak,'elapsed_seconds':time.monotonic()-started,'stdout':out.decode(),'stderr_bytes':len(err),'bundle_sha256':hashlib.sha256((s/'build/probe.bundle.js').read_bytes()).hexdigest(),'host_sha256':hashlib.sha256((s/'build/source-proof-jsc').read_bytes()).hexdigest()}
path=s/'results'/f'{stamp}-jsc-{mode}.json';path.write_text(json.dumps(record,indent=2)+'\n');print(out.decode(),end='');print('JSC sanitized receipt:',path);print('JSC guard:',reason or 'completed','peak RSS bytes:',peak);raise SystemExit(p.returncode or 0)
