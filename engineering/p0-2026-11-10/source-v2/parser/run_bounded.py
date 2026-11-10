#!/usr/bin/env python3
"""Bounded local parser/solver runner; outputs sanitized numeric JSON only."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,subprocess,time
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser')
p=argparse.ArgumentParser();p.add_argument('label');p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args()
assert a.label.replace('-','').replace('_','').isalnum()
command=a.command[1:] if a.command[:1]==['--'] else a.command
assert command and Path(command[0]).is_relative_to(ROOT/'build')
assert sum(f.lstat().st_blocks*512 for f in ROOT.rglob('*'))<400*1024*1024
assert shutil.disk_usage(ROOT).free>=40*1024**3
env=os.environ.copy();env.update(TMPDIR=str(ROOT/'tmp'),CLANG_MODULE_CACHE_PATH=str(ROOT/'module-cache'))
t=time.monotonic();process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
peak=0;reason=None
while process.poll() is None:
    row=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
    if row:peak=max(peak,int(row)*1024)
    if peak>256*1024*1024:reason='process_rss_limit'
    if time.monotonic()-t>20:reason='deadline'
    if reason:process.kill();break
    time.sleep(.02)
stdout,stderr=process.communicate();events=[]
if len(stdout)>65536:raise SystemExit('oversized result refused')
for line in stdout.splitlines():
    try:events.append(json.loads(line))
    except json.JSONDecodeError:events.append({'non_json_output_bytes':len(line)})
receipt={'label':a.label,'exit_code':process.returncode,'guard_stop':reason,'elapsed_ms':round((time.monotonic()-t)*1000),'observed_peak_rss_bytes':peak,'rss_limit_bytes':256*1024*1024,'events':events,'stderr_bytes':len(stderr),'binary_sha256':hashlib.sha256(Path(command[0]).read_bytes()).hexdigest()}
name=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'-'+a.label+'.json'
(ROOT/'results'/name).write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2));print('receipt:',name)
raise SystemExit(0 if process.returncode==0 and not reason else 1)
