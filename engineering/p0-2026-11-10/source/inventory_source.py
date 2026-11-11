#!/usr/bin/env python3
"""Read-only ownership inventory, not a cleanup executor."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess
s=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source')
out=Path(__file__).resolve().parent/'cleanup-inventory.json'
def sizes(p):
    nodes=[p]+list(p.rglob('*')) if p.is_dir() else [p]
    seen=set();allocated=logical=0
    for f in nodes:
        st=f.lstat();key=(st.st_dev,st.st_ino)
        if key in seen:continue
        seen.add(key);allocated+=st.st_blocks*512
        if f.is_file():logical+=st.st_size
    return {'allocated_bytes':allocated,'logical_file_bytes':logical}
rows=[]
retain={'iphoneos/MusesP0Source.app':'new unsigned telemetry-fixed candidate 4; unfinished probe','iphoneos/signed-calibration-3':'root-owned tested signed candidate 3, includes private profile; unfinished probe','quickjs-2026-06-04':'small pinned QuickJS source retained by coordinator for unfinished device harness','build/probe.bundle.js':'exact bundled JavaScript retained for unfinished device harness'}
for name in ('NativeHost.o','iOSMain.o','quickjs.o','dtoa.o','libregexp.o','libunicode.o','cutils.o'):
    retain['iphoneos/'+name]='frozen native object retained by coordinator for minimal unfinished device relink'
for name in ('calibration-first.m4a','calibration-next.m4a'):
    retain['iphoneos/'+name]='root-generated synthetic fixture retained by coordinator for unfinished device harness'
root_owned={'iphoneos/signed-calibration-1','iphoneos/signed-calibration-2','iphoneos/development-entitlements.plist','iphoneos/calibration-first.m4a','iphoneos/calibration-next.m4a'}
for p in sorted(s.iterdir()):
    targets=sorted(p.iterdir()) if p.name in ('iphoneos','build') else [p]
    for f in targets:
        rel=str(f.relative_to(s))
        keep=rel in retain
        is_root=rel in root_owned or rel=='iphoneos/signed-calibration-3'
        reason=retain.get(rel,'root review; superseded signing/duplicate synthetic fixture' if is_root else 'reproducible build/cache/download or failed partial; bounded receipts retained in source')
        rows.append({'path':str(f),'relative_path':rel,'owner':'root coordinator' if is_root else 'p0_source agent','action':'retain unfinished probe' if keep else 'recoverable Trash candidate; root executes','reason':reason,**sizes(f)})
lsof=subprocess.run(['lsof','+D',str(s)],capture_output=True,text=True)
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':str(s),'read_only':True,'irreversible_cleanup_authorized':False,'paths':rows,'recoverable_candidates_allocated_bytes':sum(r['allocated_bytes'] for r in rows if r['action'].startswith('recoverable')),'minimum_retained_allocated_bytes':sum(r['allocated_bytes'] for r in rows if r['action'].startswith('retain')),'actual_free_bytes':shutil.disk_usage(s).free,'lsof_exit_code':lsof.returncode,'open_file_lines':len(lsof.stdout.splitlines()),'open_files_present':bool(lsof.stdout.strip()),'raw_private_signing_or_crash_data_copied':False,'cleanup_performed':False,'bytes_recovered_by_agent':0}
out.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:v for k,v in manifest.items() if k!='paths'},indent=2))
print('Inventory SHA256:',hashlib.sha256(out.read_bytes()).hexdigest())
