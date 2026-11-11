#!/usr/bin/env python3
"""One bounded AAC/Matroska fixture with unknown stream duration for SWR drain."""
from pathlib import Path
import hashlib,json,shutil,subprocess
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio/macos-streaming/v2')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
plan=json.loads((HERE/'inputs-plan.json').read_text());ready=json.loads((ROOT/'kit/ready.json').read_text())
source=ROOT/'kit/fixtures/aac-short.wav';assert sha(source)==ready['files']['fixtures/aac-short.wav']
generator=Path(plan['generator']['path']);assert sha(generator)==plan['generator']['sha256']
assert shutil.disk_usage(ROOT).free>40*1024**3
assert sum(p.stat().st_blocks*512 for p in ROOT.parent.rglob('*') if p.is_file())+1024**2<128*1024**2
out=ROOT/'extra-fixtures';out.mkdir(exist_ok=False)
target=out/'aac-unknown-duration.mka'
command=[str(generator),'-nostdin','-v','error','-i',str(source),'-c:a','aac','-b:a','128k',str(target)]
result=subprocess.run(command,capture_output=True,timeout=20)
(out/'generator.log').write_bytes(result.stdout+result.stderr)
(out/'manifest.json').write_text(json.dumps({'input_sha256':sha(source),'generator_sha256':sha(generator),'command':command,'returncode':result.returncode,
 'output_sha256':sha(target) if target.exists() else None,'output_bytes':target.stat().st_size if target.exists() else 0,'development_generator_only':True},indent=2)+'\n')
raise SystemExit(result.returncode)
