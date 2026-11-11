#!/usr/bin/env python3
"""Remux owned encoded packets to positive/zero origins, without re-encoding."""
from pathlib import Path
import hashlib,json,shutil,subprocess
HERE=Path(__file__).resolve().parent;ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-streaming/v2')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((HERE/'inputs-plan.json').read_text());generator=Path(plan['generator']['path']);assert sha(generator)==plan['generator']['sha256']
assert shutil.disk_usage(ROOT).free>40*1024**3
assert sum(p.stat().st_blocks*512 for p in ROOT.parent.rglob('*') if p.is_file())+1024**2<128*1024**2
OUT=ROOT/'timeline-fixtures';OUT.mkdir(exist_ok=False)
mka=ROOT/'extra-fixtures/aac-unknown-duration.mka';mp4=ROOT/'kit/fixtures/aac-positive-offset.m4a'
commands=[([str(generator),'-nostdin','-v','error','-i',str(mka),'-c','copy','-output_ts_offset','1',str(OUT/'aac-positive.mka')],'positive-mka'),
 ([str(generator),'-nostdin','-v','error','-copyts','-start_at_zero','-i',str(mp4),'-c','copy','-movflags','+faststart',str(OUT/'aac-normalized.m4a')],'normalized-mp4')]
for command,label in commands:
 result=subprocess.run(command,capture_output=True,timeout=20);(OUT/(label+'.log')).write_bytes(result.stdout+result.stderr)
 assert result.returncode==0,(label,result.returncode)
probe=generator.parent/'ffprobe';reports={}
for path in (mka,mp4,OUT/'aac-positive.mka',OUT/'aac-normalized.m4a'):
 result=subprocess.run([str(probe),'-v','error','-select_streams','a','-show_streams','-show_packets','-show_data_hash','sha256','-show_entries','stream=start_time,duration,time_base:packet=data_hash','-of','json',str(path)],capture_output=True,timeout=20)
 assert result.returncode==0;value=json.loads(result.stdout)
 reports[path.name]={'sha256':sha(path),'bytes':path.stat().st_size,'streams':value['streams'],'packet_hashes':[p['data_hash'] for p in value['packets']]}
assert reports[mka.name]['packet_hashes']==reports['aac-positive.mka']['packet_hashes']
assert reports[mp4.name]['packet_hashes']==reports['aac-normalized.m4a']['packet_hashes']
(OUT/'manifest.json').write_text(json.dumps({'generator_sha256':sha(generator),'probe_sha256':sha(probe),'commands':[x[0] for x in commands],'representations':reports,'encoded_packet_hash_sequences_equal':True,'development_tools_only':True},indent=2)+'\n')
print(json.dumps({name:value['streams'] for name,value in reports.items()}))
