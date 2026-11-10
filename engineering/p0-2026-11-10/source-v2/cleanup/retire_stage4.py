#!/usr/bin/env python3
"""Stage 4 adapter: verify a frozen inventory, journal recoverable renames only.

Derived from the frozen root retire_scratch.py journal/resume workflow.
Dry-run is the default. This file has NOT been invoked with --execute.
"""
import argparse,hashlib,json,os,shutil,stat,subprocess,time
from pathlib import Path

ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
TRASH=Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01/stage4')
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def scan(path):
    rows=[];stack=[path];unique={};logical=allocated=0
    while stack:
        p=stack.pop();s=p.lstat()
        assert s.st_uid==os.getuid(),'owner mismatch: '+str(p)
        assert stat.S_ISDIR(s.st_mode) or stat.S_ISREG(s.st_mode),'unexpected node: '+str(p)
        row={'relative':str(p.relative_to(path)),'device':s.st_dev,'inode':s.st_ino,'uid':s.st_uid,'gid':s.st_gid,
             'mode':s.st_mode,'logical_bytes':s.st_size if p.is_file() else 0,'allocated_bytes':s.st_blocks*512,
             'size':s.st_size,'mtime_ns':s.st_mtime_ns}
        if p.is_file():row['sha256']=digest(p);logical+=s.st_size
        else:stack.extend(sorted(p.iterdir(),reverse=True))
        rows.append(row);allocated+=s.st_blocks*512;unique[(s.st_dev,s.st_ino)]=s.st_blocks*512
    frozen=json.dumps(rows,sort_keys=True,separators=(',',':')).encode()
    return {'entries':len(rows),'logical_file_bytes':logical,'allocated_bytes':allocated,
            'allocated_unique_inode_bytes':sum(unique.values()),'uid':os.getuid(),
            'tree_sha256':hashlib.sha256(frozen).hexdigest()},rows
def handles(path):
    cmd=['lsof','-nP','+D',str(path)] if path.is_dir() else ['lsof','-nP',str(path)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
    assert r.returncode==1 and not r.stdout and not r.stderr,'active or inconclusive handles: '+str(path)
    return {'returncode':r.returncode,'stdout_bytes':0,'stderr_bytes':0,'open_handles':0}
def processes(paths):
    r=subprocess.run(['ps','-axo','pid=,uid=,comm=,args='],capture_output=True,text=True,check=True)
    found=[]
    for line in r.stdout.splitlines():
        values=line.strip().split(None,3)
        if len(values)!=4:continue
        for path in paths:
            if str(path) in values[3]:
                found.append({'pid':int(values[0]),'uid':int(values[1]),'command_name':Path(values[2]).name,'matched_path':str(path)})
    return found
def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--plan-sha256',required=True)
    p.add_argument('--script-sha256',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args()
    assert digest(Path(__file__))==a.script_sha256
    assert digest(a.plan)==a.plan_sha256
    plan=json.loads(a.plan.read_text());assert plan['owned_root']==str(ROOT) and plan['trash_root']==str(TRASH)
    assert plan['script_sha256']==a.script_sha256
    for item in plan['required_manifests']:assert digest(Path(item['path']))==item['sha256'],'retained evidence changed'
    sources=[Path(item['source']) for item in plan['moves']]
    assert len(set(sources))==len(sources)
    assert not any(a!=b and a.is_relative_to(b) for a in sources for b in sources),'overlapping sources'
    journal_path=a.plan.with_name(a.plan.stem+'-journal.json')
    journal=json.loads(journal_path.read_text()) if journal_path.exists() else {
        'plan_sha256':a.plan_sha256,'script_sha256':a.script_sha256,'started_unix':time.time(),
        'free_before':shutil.disk_usage(ROOT).free,'actions':[],'failures':[]}
    assert journal['plan_sha256']==a.plan_sha256 and journal['script_sha256']==a.script_sha256
    def save():
        temp=journal_path.with_suffix('.pending');temp.write_text(json.dumps(journal,indent=2)+'\n');temp.replace(journal_path)
    try:
        checks=[]
        for item in plan['moves']:
            src=Path(item['source']);dst=TRASH/item['destination_name']
            assert src.is_relative_to(ROOT) and src!=ROOT and dst.parent==TRASH
            assert not src.is_symlink() and not dst.is_symlink()
            actions=[x for x in journal['actions'] if x['source']==str(src)]
            assert len(actions)<=1,'duplicate journal action'
            if actions and actions[0]['complete']:
                assert not src.exists() and dst.exists(),'completed move changed'
                location=dst
            elif actions and not src.exists() and dst.exists():location=dst
            else:
                assert src.exists() and not dst.exists(),'ambiguous source/destination'
                location=src
            assert location.resolve()==location,'symlinked path component'
            measured,_=scan(location);assert measured==item['required_inventory'],'frozen source inventory changed: '+str(src)
            checks.append({'source':str(src),'verified_location':str(location),'inventory':measured,'handles':handles(location)})
        active=processes([Path(x['verified_location']) for x in checks]);assert not active,'candidate process still active'
        if not a.execute:
            print(json.dumps({'preflight':True,'executed':False,'paths':len(checks),'journal_written':False,'active_processes':active}));return
        save()
        for item in plan['moves']:
            src=Path(item['source']);dst=TRASH/item['destination_name']
            actions=[x for x in journal['actions'] if x['source']==str(src)]
            if actions and actions[0]['complete']:continue
            if actions and not src.exists() and dst.exists():
                assert scan(dst)[0]==item['required_inventory'],'interrupted destination changed'
                actions[0]['complete']=True;actions[0]['reconciled_after_interruption']=time.time();save();continue
            handles(src);assert not processes([src]),'candidate process appeared'
            before,_=scan(src);assert before==item['required_inventory'],'source changed after preflight'
            TRASH.mkdir(parents=True,exist_ok=True)
            assert TRASH.resolve()==TRASH and src.stat().st_dev==TRASH.stat().st_dev,'not an exact same-volume destination'
            if not actions:
                journal['actions'].append({'source':str(src),'destination':str(dst),'inventory':before,'complete':False,'open_handles':0,'time_unix':time.time()})
                actions=[journal['actions'][-1]]
            save();src.rename(dst)
            assert scan(dst)[0]==before,'post-rename inventory changed'
            actions[0]['complete']=True;save()
        journal['completed_unix']=time.time();journal['free_after']=shutil.disk_usage(ROOT).free
        journal['physical_recovery_claim_bytes']=0;save()
        print(json.dumps({'complete':True,'moved_paths':len(journal['actions']),'allocated_path_sum_bytes':sum(x['inventory']['allocated_bytes'] for x in journal['actions']),'free_before':journal['free_before'],'free_after':journal['free_after'],'physical_recovery_claim_bytes':0}))
    except BaseException as error:
        if a.execute:journal['failures'].append({'time_unix':time.time(),'type':type(error).__name__,'message':str(error)});save()
        raise
if __name__=='__main__':main()
