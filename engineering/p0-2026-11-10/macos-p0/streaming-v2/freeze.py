#!/usr/bin/env python3
"""Freeze bounded text evidence and exact cleanup inventory; never remove files."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,time
HERE=Path(__file__).resolve().parent;ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
OWNED=ROOT/'audio/macos-streaming/v2';PLAN=HERE/'freeze-plan.json';EVIDENCE=HERE/'evidence'
FINAL='build-20261111-004247'
RETAIN={FINAL,'kit','extra-fixtures','timeline-fixtures','current-build.txt'}
RECEIPTS='03fcb7b25e3d4d30967777700e06c4de 4e8b4d8687f9416594c957694e88ff4a db31b1567c0b4864a3fbedb1d084596a 1e465c71627d42199a3f2c44dd2c42f1 13a27035e2864e62aa771d3432ffebad 57fc07b4b0034f9f9477565748681ec4 a46dfc96351749309444bee49d2763b7 5cdb5db390c14f2eb36bb018184eb2d8 36ce774be93b4987ade992b5275707c2 d99898036f4c48b38c0c86ff648a37c5 5373403580e74fe6bc8770445bad5d0a f92c60e429a341bf87d7705af1870225 d936b20c9c6c490f9dd5041cd785246a 5a21f1aad79d4f088f7e41c5b8fef8d0 b9724cfad26948f4a9e083899c3587f1 d34c1ff0b4474399aa12e76883cbdcec 818247c8928a44d4939598903433695d 101b3d2f0f4d4699baac21da9b206ea8 7fa02e6627c14fd79a4fe50e05dbeb5d 84fd7f152b6542d898857330ab3604e9 ab3887edff0248afa21f71102cc01508 76886d9ebb1e4614b821ea5f61dba94c'.split()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def files(p):return sorted(x for x in p.rglob('*') if x.is_file()) if p.is_dir() else [p]
def allocated(p):return sum(x.stat().st_blocks*512 for x in files(p))
def sources():return {str(p):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and EVIDENCE not in p.parents and p!=PLAN}
def check():
 assert sha(HERE/'budget.json')=='a1273271ae7b72d860811c7b9ce3ed59c9249c52c32938b8037ff8566c21b034'
 assert sha(HERE/'Streaming.cpp')=='b1adba3d2375676d270a144dcd8b3e92463173ea0d671c951e7e7a58b2b19b28'
 assert sha(HERE/'REVIEW-V2.md')=='3964193ae8a54060924bab050454afbe5e9d1fd484fa9a41d4b0d9384c9ad8eb'
 assert allocated(OWNED)<96*1024**2 and allocated(OWNED.parent)<128*1024**2
 assert shutil.disk_usage(ROOT).free>40*1024**3
def prepare():
 assert not PLAN.exists();check();copies=[]
 def add(path,destination):
  assert path.is_file() and not path.is_symlink();copies.append({'source':str(path),'destination':str(destination),'sha256':sha(path),'bytes':path.stat().st_size})
 for directory in sorted(OWNED.iterdir()):
  if not directory.is_dir():continue
  if directory.name=='kit':add(directory/'ready.json',Path('kit-ready.json'));continue
  for path in sorted(directory.iterdir()):
   if path.is_file() and (path.suffix in ('.json','.jsonl','.log') or path.name in ('SourceResolver.m','stream_source.h')):
    add(path,Path(directory.name)/path.name)
 for name in RECEIPTS:add(ROOT/'coordination/receipts'/(name+'.json'),Path('receipts')/(name+'.json'))
 assert sum(row['bytes'] for row in copies)<2*1024**2
 dump(PLAN,{'script_sha256':sha(Path(__file__)),'source_sha256':sources(),'copies':copies,
  'scope':'Copy bounded evidence and read-only ownership inventory; no cleanup execution','output_limit_bytes':3*1024**2,'retained_names':sorted(RETAIN)})
 print(json.dumps({'plan_sha256':sha(PLAN),'script_sha256':sha(Path(__file__)),'copy_files':len(copies),'copy_bytes':sum(row['bytes'] for row in copies)}))
def freeze(expected):
 assert sha(PLAN)==expected;plan=json.loads(PLAN.read_text());assert sha(Path(__file__))==plan['script_sha256'];assert sources()==plan['source_sha256'];check()
 assert not EVIDENCE.exists();EVIDENCE.mkdir()
 for row in plan['copies']:
  source=Path(row['source']);assert sha(source)==row['sha256'];target=EVIDENCE/row['destination'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);assert sha(target)==row['sha256']
 opened=subprocess.run(['lsof','-nP','+D',str(OWNED)],capture_output=True,text=True,timeout=30);assert opened.returncode in (0,1)
 process=subprocess.run(['ps','-axo','pid,ppid,comm'],capture_output=True,text=True,check=True)
 active=[line for line in process.stdout.splitlines() if str(OWNED)+'/' in line and any('/'+name in line for name in ('stream-local','stream-public','reference','inspect'))]
 assert not active,'active native process';paths=[]
 for path in sorted(OWNED.iterdir()):
  entries=files(path);paths.append({'path':str(path),'owner':'P0 audio streaming-v2 subagent','disposition':'retain_minimum_current_kit' if path.name in RETAIN else 'eligible_for_coordinator_recoverable_stage7_cleanup',
   'logical_bytes':sum(p.stat().st_size for p in entries),'allocated_file_blocks_bytes':sum(p.stat().st_blocks*512 for p in entries),
   'files':[{'relative_path':str(p.relative_to(path)) if path.is_dir() else p.name,'bytes':p.stat().st_size,'allocated_bytes':p.stat().st_blocks*512,'sha256':sha(p)} for p in entries]})
 inventory={'observed_unix':time.time(),'paths':paths,'active_native_processes':active,'lsof_exit_code':opened.returncode,'lsof_stdout':opened.stdout,'lsof_stderr':opened.stderr,
  'logical_bytes':sum(p['logical_bytes'] for p in paths),'allocated_file_blocks_bytes':sum(p['allocated_file_blocks_bytes'] for p in paths),
  'retained_allocated_file_blocks_bytes':sum(p['allocated_file_blocks_bytes'] for p in paths if p['disposition'].startswith('retain')),
  'eligible_allocated_file_blocks_bytes':sum(p['allocated_file_blocks_bytes'] for p in paths if p['disposition'].startswith('eligible')),
  'actual_free_bytes_at_observation':shutil.disk_usage(ROOT).free,'cleanup_executed':False,'physical_bytes_recovered_by_this_agent':0,
  'note':'File block totals are not an APFS recovery measurement. Original public media/source/relink/v1 paths are outside this cleanup scope.'}
 dump(EVIDENCE/'cleanup-inventory.json',inventory)
 toolchain={}
 for name,command in [('macos',['sw_vers']),('xcode',['xcodebuild','-version']),('clang',['clang','--version']),('sdk',['xcrun','--sdk','macosx','--show-sdk-path'])]:
  value=subprocess.run(command,capture_output=True,text=True,check=True);toolchain[name]={'command':command,'stdout':value.stdout,'stderr':value.stderr}
 dump(EVIDENCE/'toolchain.json',toolchain)
 current=json.loads((OWNED/FINAL/'success.json').read_text())
 assert all(sha(OWNED/FINAL/name)==digest for name,digest in current['binary_sha256'].items())
 assert all(sha(Path(path))==digest for path,digest in current['source_sha256'].items())
 evidence={str(p.relative_to(EVIDENCE)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(EVIDENCE.rglob('*')) if p.is_file()}
 assert sum(row['bytes'] for row in evidence.values())<plan['output_limit_bytes'];assert sources()==plan['source_sha256']
 dump(EVIDENCE/'manifest.json',{'frozen_unix':time.time(),'freeze_plan_sha256':sha(PLAN),'freeze_script_sha256':sha(Path(__file__)),'source_sha256':sources(),
  'authoritative_build':FINAL,'authoritative_local':'local-20261111-004309','authoritative_public':'public-20261111-004412',
  'binary_sha256':current['binary_sha256'],'files':evidence,'speaker_first_sound_measured':False,'macos_26_executed':False,'production_application_integrated':False,'cleanup_executed':False})
 print(json.dumps({'manifest_sha256':sha(EVIDENCE/'manifest.json'),'evidence_files':len(evidence),'evidence_bytes':sum(row['bytes'] for row in evidence.values()),
  'eligible_allocated_bytes':inventory['eligible_allocated_file_blocks_bytes'],'retained_allocated_bytes':inventory['retained_allocated_file_blocks_bytes'],'scratch_allocated_bytes':inventory['allocated_file_blocks_bytes']}))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--plan-sha');args=parser.parse_args();prepare() if args.prepare else freeze(args.plan_sha)
