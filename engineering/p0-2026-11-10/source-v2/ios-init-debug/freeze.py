#!/usr/bin/env python3
"""Freeze bounded offline evidence and a read-only retirement inventory."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess
HERE=Path(__file__).resolve().parent
SCRATCH=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/ios-init-debug')
EVIDENCE=HERE/'evidence';EVIDENCE.mkdir(exist_ok=True)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():assert path.read_bytes()==data, f'frozen output already differs: {path.name}'
    else:path.write_bytes(data)
def putjson(path,data):put(path,(json.dumps(data,indent=2,ensure_ascii=False)+'\n').encode())
old='20261110T230424.597930Z';fixed='20261110T231352.377950Z-corrected'
for path in sorted((SCRATCH/'results').iterdir()):
    assert path.name.startswith((old,fixed)) and path.is_file()
    put(EVIDENCE/'raw'/path.name,path.read_bytes())
snapshots=[('inputs/NativeHost.v2.m','candidate5.NativeHost.v2.m','90e9952071fee1f3eb193538399ba85d43b9390fc9a156e64c656b9a74ddb5ce'),('corrected-inputs/NativeHost.v2.m','corrected.NativeHost.v2.m','f37159192477d9ddc8316d96f7884185d59b27e301e1152124bb684e99dd5fa8'),('corrected-inputs/NativeInput.inc','NativeInput.inc','aa93db0a62f144dd8faf512a1a083c4ee17a45dfa7ad8d17720ef74adbfa7963'),('corrected-inputs/isolated-fixture.js','isolated-fixture.js',None)]
for rel,name,expected in snapshots:
    source=SCRATCH/rel
    if expected:assert sha(source)==expected
    put(EVIDENCE/'inputs'/name,source.read_bytes())
receipts=SCRATCH.parents[2]/'coordination/receipts'
for name,identifier in [('old','ed673df112634c17a60c9e56ba157650'),('corrected','5bd447916b3247a9a492fb91bbbe5f1e')]:
    path=receipts/(identifier+'.json');receipt=json.loads(path.read_text());assert receipt['returncode']==0 and receipt['stop_reason'] is None
    put(EVIDENCE/('guard-'+name+'.json'),path.read_bytes())
old_runs=[];corrected_runs=[]
for path in sorted((EVIDENCE/'raw').glob('*.json')):
    record=json.loads(path.read_text());events=record.get('events',[])
    if not events:continue
    assert record['exit_code']==0 and record['guard_stop'] is None
    if path.name.startswith(old):
        cases=[e for e in events if e.get('phase')=='case'];assert all(e['expected'] and e['shape_ok'] for e in cases)
        old_runs.append({'receipt':'raw/'+path.name,'label':record['label'],'cases':len(cases),'exception_cases':sum(e['exception_category']!='none' for e in cases),'js_peak_values':sorted(set(e['js_peak_bytes'] for e in cases)),'maxrss_bytes':max(e.get('process_maxrss_bytes',0) for e in events)})
    else:
        summary=next(e for e in events if e.get('gate')=='corrected_input_summary');assert summary['outcome']=='pass' and summary['failures']==0 and summary['terminator_failures']==0
        corrected_runs.append({'receipt':'raw/'+path.name,'label':record['label'],**{key:value for key,value in summary.items() if key!='gate'}})
assert sum(x['cases'] for x in old_runs)==70 and sum(x['exception_cases'] for x in old_runs)==13
assert sum(x['checks'] for x in corrected_runs)==56
putjson(EVIDENCE/'summary.json',{'old':{'cases':70,'expected_syntax_failures':13,'successful_initializations':57,'maxrss_bytes':max(x['maxrss_bytes'] for x in old_runs),'runs':old_runs},'corrected':{'checks':56,'eval_inputs_verified_terminated':66,'actual_bundle_executions':22,'network_requests':0,'maxrss_bytes':max(x['process_maxrss_bytes'] for x in corrected_runs),'runs':corrected_runs},'phone_causation':'matching deterministic failure signature; original phone exception type and trailer bytes were not retained','phone_retest':'deferred by user; no new phone action'})
qjs=SCRATCH.parents[1]/'quickjs-2026-06-04'
provenance={'bundle':{'bytes':(SCRATCH/'inputs/probe.bundle.js').stat().st_size,'sha256':sha(SCRATCH/'inputs/probe.bundle.js'),'origin':'exact candidate-5 app bundle copy; no network acquisition in this diagnostic'},'quickjs':{'version':'2026-06-04','header_sha256':sha(qjs/'quickjs.h'),'implementation_sha256':sha(qjs/'quickjs.c'),'api_contract':'quickjs.h:835','parser_eof':'quickjs.c:22727-22735','parser_bounds':'quickjs.c:37013-37021','new_runtime_stack_top':'quickjs.c:2116'},'host_snapshots':{name:sha(EVIDENCE/'inputs'/name) for _,name,_ in snapshots},'old_build_manifest':'raw/'+old+'-manifest.json','corrected_build_manifest':'raw/'+fixed+'-manifest.json','test_sources':{name:sha(HERE/name) for name in ['driver.m','run.py','corrected-driver.m','run-corrected.py']}}
putjson(EVIDENCE/'provenance.json',provenance)
lsof=subprocess.run(['lsof','-nP','+D',str(SCRATCH)],capture_output=True,text=True,timeout=30)
assert lsof.returncode in (0,1) and not lsof.stdout.strip() and not lsof.stderr.strip(),'open-file audit not empty'
processes=subprocess.run(['ps','-axo','pid=,command='],capture_output=True,text=True,check=True)
matches=[]
for row in processes.stdout.splitlines():
    parts=row.strip().split(maxsplit=1)
    if len(parts)!=2:continue
    pid,command=int(parts[0]),parts[1]
    if pid in (os.getpid(),os.getppid()):continue
    if str(SCRATCH) in command and any(name in command for name in ['/driver','/corrected-driver','/run.py','/run-corrected.py']):matches.append({'pid':pid,'command':command})
assert not matches,'diagnostic process remains active'
entries=[];logical=0;allocated=0;seen=set()
for path in [SCRATCH,*sorted(SCRATCH.rglob('*'))]:
    stat=path.lstat();key=(stat.st_dev,stat.st_ino);assert stat.st_uid==os.getuid() and not path.is_symlink()
    row={'path':str(path.relative_to(SCRATCH)) or '.','type':'directory' if path.is_dir() else 'file','uid':stat.st_uid,'gid':stat.st_gid,'logical_bytes':stat.st_size if path.is_file() else 0,'allocated_bytes':stat.st_blocks*512,'mtime_ns':stat.st_mtime_ns}
    if path.is_file():row['sha256']=sha(path);logical+=stat.st_size
    if key not in seen:allocated+=stat.st_blocks*512;seen.add(key)
    entries.append(row)
assert allocated<20*1024**2
putjson(EVIDENCE/'scratch-retirement.json',{'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'path':str(SCRATCH),'owner':'p0_interop; completed offline initialization diagnosis','uid':os.getuid(),'logical_bytes':logical,'allocated_bytes_unique_inode_including_directories':allocated,'per_path_allocated_bytes':sum(e['allocated_bytes'] for e in entries),'hardlinks':len(entries)-len(seen),'scratch_limit_bytes':20*1024**2,'current_free_bytes':shutil.disk_usage(SCRATCH).free,'lsof_returncode':lsof.returncode,'lsof_stdout_bytes':0,'lsof_stderr_bytes':0,'matching_active_processes':matches,'retirement_status':'eligible for root frozen stage-4 recoverable move; not executed here','files':entries})
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'immutable offline input-contract evidence; current manifests and old attempt manifests intentionally distinct','files':{str(path.relative_to(HERE)):{'sha256':sha(path),'bytes':path.stat().st_size} for path in sorted(HERE.rglob('*')) if path.is_file() and path.name!='source-hashes.json'}}
putjson(HERE/'source-hashes.json',manifest)
print(json.dumps({'manifest_sha256':sha(HERE/'source-hashes.json'),'files':len(manifest['files']),'scratch_logical_bytes':logical,'scratch_allocated_bytes':allocated,'lsof_open_files':0,'active_diagnostic_processes':0,'scratch_inventory_sha256':sha(EVIDENCE/'scratch-retirement.json')}))
