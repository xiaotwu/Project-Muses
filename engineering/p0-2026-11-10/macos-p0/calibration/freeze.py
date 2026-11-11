#!/usr/bin/env python3
"""Freeze calibration preparation evidence; never launch, capture, or clean."""
from pathlib import Path
import datetime,hashlib,json,os,plistlib,shutil,subprocess
HERE=Path(__file__).resolve().parent
SCRATCH=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/interop/macos-calibration')
EVIDENCE=HERE/'evidence';EVIDENCE.mkdir(exist_ok=True)
FINAL='20261110T235039.849228Z'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():assert path.read_bytes()==data,'frozen output differs: '+str(path)
    else:path.write_bytes(data)
def putjson(path,data):put(path,(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode())
attempts=[]
for directory in sorted((SCRATCH/'attempts').iterdir()):
    manifest=json.loads((directory/'manifest.json').read_text())
    for path in sorted(directory.rglob('*')):
        if path.is_file() and (path.suffix in ['.stdout','.stderr','.json'] or 'source-before-cancel-fix' in path.parts):
            put(EVIDENCE/'attempts'/directory.name/path.relative_to(directory),path.read_bytes())
    attempts.append({'id':directory.name,'manifest':'attempts/'+directory.name+'/manifest.json','app_binary_sha256':manifest.get('app',{}).get('binary_sha256'),'test':manifest.get('offline_test'),'status':'current_unlaunched_candidate' if directory.name==FINAL else 'superseded_or_failed_preserved'})
receipt_ids={'initial_compile_failure':'3a10eb13c421445f91d91d082d02f1e0','predecessor_42_checks':'42c85b008fa8446783a8de45231759b8','pre_fix_44_checks':'2ee49145f97243de9ad10ae1012f66b7','pre_fix_source_snapshot':'582c917e779e4795953f72be9508fb69','final_46_checks':'546b225a89264e40af2f55722c075aeb'}
for label,identifier in receipt_ids.items():put(EVIDENCE/'guards'/(label+'.json'),(SCRATCH.parents[1]/'coordination/receipts'/(identifier+'.json')).read_bytes())
final_dir=SCRATCH/'attempts'/FINAL;manifest=json.loads((final_dir/'manifest.json').read_text())
for name,value in manifest['source_hashes'].items():assert sha(HERE/name)==value
assert manifest['source_hashes']==manifest['source_hashes_after']
app=Path(manifest['app']['path']);binary=app/'Contents/MacOS/MusesAcousticCalibration'
assert sha(binary)==manifest['app']['binary_sha256']=='7184357322ede54435e316fc246e4fa84a527be45d6503c9f06ae9db439d5dfa'
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
assert info['P0CalibrationSourceSetSHA256']==hashlib.sha256(json.dumps(manifest['source_hashes'],sort_keys=True).encode()).hexdigest()
rows=[json.loads(line) for line in (final_dir/'tests.stdout').read_text().splitlines()]
assert rows[-1]['summary']=='pass' and rows[-1]['checks']==46 and rows[-1]['failures']==0
positive=[r for r in rows if 'measurement' in r]
putjson(EVIDENCE/'summary.json',{'status':'offline_preparation_complete_physical_validation_pending','current_app':manifest['app'],'current_build_manifest':'attempts/'+FINAL+'/manifest.json','source_set_sha256':info['P0CalibrationSourceSetSHA256'],'offline_summary':rows[-1],'positive_cases':len(positive),'maximum_synthetic_reference_error_us':max(abs(x) for r in positive for x in r['reference_error_us']),'minimum_positive_correlation':min(x for r in positive for x in r['correlation']),'maximum_resolution_component_ms':max(r['detector_bound_ms'] for r in positive),'guards':receipt_ids,'attempts':attempts,'physical_actions':{'app_launch':False,'permission_request':False,'microphone_capture':False,'audible_output':False},'physical_total_error_bound_ms':None,'campaign_metric_generated':False,'review':{'reviewer':'independent source agent','cancel_finish_race':'fixed and reviewed at source ad20e33663e0f8163163ffd4218537e901fa172dc9c0bf5a7812f8fce19cf87b','final_review_findings':'no other concrete safety blocker found; framework RSS, shutdown latency and fixed physical timestamp bias remain unmeasured'}})
lsof=subprocess.run(['lsof','-nP','+D',str(SCRATCH)],capture_output=True,text=True,timeout=30)
assert lsof.returncode in (0,1) and not lsof.stderr.strip()
processes=subprocess.run(['ps','-axo','pid=,comm='],capture_output=True,text=True,check=True)
active=[]
for line in processes.stdout.splitlines():
    parts=line.strip().split(maxsplit=1)
    if len(parts)==2 and (str(SCRATCH) in parts[1] or parts[1].endswith('/MusesAcousticCalibration')):active.append({'pid':int(parts[0]),'executable':parts[1]})
putjson(EVIDENCE/'runtime-handoff.json',{'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'root_confirmed_launch_and_idle_UI_check':True,'root_reported_explicit_user_consent_for_one_short_capture':True,'physical_result_owner':'root; not part of offline preparation test results','current_app_retained':str(app),'active_app_processes':active,'lsof_returncode':lsof.returncode,'lsof_stdout':lsof.stdout,'failed_zero_handle_freeze':'freeze-attempts/4f62ce047274406184ffb00e893be740/guard.json','cleanup_executed':False})
entries=[];seen=set();logical=0;allocated=0
runtime_receipts=SCRATCH/'receipts'
for path in [SCRATCH,*sorted(SCRATCH.rglob('*'))]:
    if path==runtime_receipts or runtime_receipts in path.parents:continue
    stat=path.lstat();assert stat.st_uid==os.getuid() and not path.is_symlink();key=(stat.st_dev,stat.st_ino)
    row={'path':str(path.relative_to(SCRATCH)) or '.','uid':stat.st_uid,'gid':stat.st_gid,'type':'directory' if path.is_dir() else 'file','logical_bytes':stat.st_size if path.is_file() else 0,'allocated_bytes':stat.st_blocks*512,'mtime_ns':stat.st_mtime_ns,'retention':'required_current_app' if path==app or app in path.parents else 'completed_or_superseded_helper'}
    if path.is_file():row['sha256']=sha(path);logical+=stat.st_size
    if key not in seen:allocated+=stat.st_blocks*512;seen.add(key)
    entries.append(row)
assert allocated<64*1024**2
obsolete_dirs=[str(p) for p in sorted((SCRATCH/'attempts').iterdir()) if p.name!=FINAL]
obsolete_current_files=[str(p) for p in sorted(final_dir.iterdir()) if p.is_file()]
putjson(EVIDENCE/'scratch-inventory.json',{'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'owner':'p0_interop acoustic calibration preparation; final app now held by root','uid':os.getuid(),'scratch':str(SCRATCH),'scratch_limit_bytes':64*1024**2,'logical_bytes_excluding_active_runtime_receipts':logical,'allocated_bytes_unique_inode_excluding_active_runtime_receipts':allocated,'per_path_allocated_bytes':sum(x['allocated_bytes'] for x in entries),'hardlink_difference_bytes':sum(x['allocated_bytes'] for x in entries)-allocated,'excluded_active_subtrees':[str(runtime_receipts)],'free_bytes':shutil.disk_usage(SCRATCH).free,'retained_app':str(app),'obsolete_attempt_directories':obsolete_dirs,'completed_current_attempt_helper_files':obsolete_current_files,'lsof_record':'runtime-handoff.json','lsof_returncode':lsof.returncode,'active_processes':active,'cleanup_executed':False,'system_residue_status':'root has begun separate authorized app/physical check; registration/preferences/permission state and runtime results require root final inventory','files':entries})
files={str(p.relative_to(HERE)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='source-hashes.json'}
putjson(HERE/'source-hashes.json',{'scope':'final calibration preparation and immutable old attempts','files':files})
print(json.dumps({'manifest_sha256':sha(HERE/'source-hashes.json'),'files':len(files),'evidence_bytes':sum(r['bytes'] for r in files.values()),'inventory_sha256':sha(EVIDENCE/'scratch-inventory.json'),'inventoried_logical_bytes':logical,'inventoried_allocated_bytes':allocated,'obsolete_directories':len(obsolete_dirs),'active_app_processes':len(active),'lsof_data_rows':max(0,len(lsof.stdout.splitlines())-1),'current_app_retained_for_root':True}))
