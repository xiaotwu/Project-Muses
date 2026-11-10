#!/usr/bin/env python3
"""Preserve bounded control evidence and inventory owned scratch for parent cleanup."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/control')
GUARDS=ROOT.parents[2]/'coordination/receipts'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(HERE.parent/'NativeControl.inc')=='0876bc263d605cd68eb0c8b9b308da39dfc90d437784517722a70f325604091e'
def copy(p,target):
    data=p.read_bytes()
    if target.exists():assert target.read_bytes()==data
    else:target.write_bytes(data)
evidence=HERE/'evidence';evidence.mkdir(exist_ok=True)
for folder in [ROOT/'results',ROOT/'host-wiring/results']:
    for p in sorted(folder.iterdir()):
        assert p.is_file() and p.stat().st_size<128*1024
        copy(p,evidence/p.name)
copy(ROOT/'host-wiring/inputs/desktop-build.json',evidence/'host-wiring-desktop-build.json')
for name in ['b0617b5fd04d42b39b1c6efa1448436f','50e5755d6503402fab0c706f02afa0f1']:
    copy(GUARDS/(name+'.json'),evidence/('guard-'+name+'.json'))
opened=subprocess.run(['lsof','+D',str(ROOT)],capture_output=True,text=True)
assert opened.returncode in [0,1] and not opened.stdout.strip()
files=[];inodes={}
for p in [ROOT,*sorted(ROOT.rglob('*'))]:
    st=p.lstat();assert not p.is_symlink();inodes[(st.st_dev,st.st_ino)]=st.st_blocks*512
    if p.is_file():files.append({'path':str(p),'logical_bytes':st.st_size,'allocated_bytes':st.st_blocks*512,'sha256':sha(p)})
inventory={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate_root':str(ROOT),'files':files,'logical_file_bytes':sum(p['logical_bytes'] for p in files),'allocated_unique_inode_bytes':sum(inodes.values()),'scratch_limit_bytes':10*1024**2,'actual_free_bytes':shutil.disk_usage(ROOT).free,'active_process_handles':[],'open_files':[],'lsof_exit_code':opened.returncode,'deletion_performed':False,'scope':'Only owned obsolete local control proof scratch; parent performs frozen recoverable cleanup. Small raw receipts are retained under control/evidence.'}
assert inventory['allocated_unique_inode_bytes']<inventory['scratch_limit_bytes']
(HERE/'cleanup-candidates.json').write_text(json.dumps(inventory,indent=2)+'\n')
manifest={'source_sha256':{'../NativeControl.inc':sha(HERE.parent/'NativeControl.inc')},'files':{str(p.relative_to(HERE)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='manifest.json'},'module_checks':122,'host_wiring_checks':42,'network_requests':0,'device_runtime_tested':False}
(HERE/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'manifest_sha256':sha(HERE/'manifest.json'),'frozen_files':len(manifest['files']),'scratch_allocated_bytes':inventory['allocated_unique_inode_bytes'],'scratch_logical_file_bytes':inventory['logical_file_bytes'],'open_files':0},indent=2))
