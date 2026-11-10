#!/usr/bin/env python3
"""Keep bounded logs/manifests/journals, not libraries or compiler caches."""
from pathlib import Path
import hashlib,json,shutil,subprocess
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport')
P0=HERE.parents[1]
OUT=HERE/'evidence';OUT.mkdir(exist_ok=True)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def copy(p,relative):
    assert p.stat().st_size<1024*1024
    target=OUT/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
selected={
 'transport':sorted(p for p in ROOT.iterdir()if p.is_dir()and p.name.startswith('202'))[-1],
 'avio':sorted(ROOT.glob('avio-*'))[-1],
 'generic':sorted(ROOT.glob('decoder-probe-*'))[-1],
 'long':sorted(p for p in ROOT.glob('long-*')if p.name!='long-fixtures')[-1],
}
for label,folder in selected.items():
    for path in folder.iterdir():
        if path.is_file()and path.suffix in ['.log','.json','.jsonl','.txt']:
            copy(path,Path(label)/path.name)
copy(ROOT/'decoder-inputs/provenance.json',Path('decoder-input-provenance.json'))
copy(ROOT/'narrow-headers-plan.json',Path('recovery/narrow-headers-plan.json'))
copy(ROOT/'narrow-headers-journal.jsonl',Path('recovery/narrow-headers-journal.jsonl'))
commands=[]
for name in ['run_local.py','build_objects.py','restore_decoder_inputs.py','run_avio.py','build_decode_probe.py','run_long.py']:
    commands.append(['python3',str(HERE/name)])
commands += [['python3',str(HERE/'narrow_headers.py'),'prepare'],
 ['python3',str(HERE/'narrow_headers.py'),'execute','5cdd21d8bc5651d90d8e0d2164b77180cac2e3c637c0675d06ab1a313c2ae7cb','2c9e6cc9fb23c8dce42183fdd1e99f67c62bda3b4f75710ef40fe108d684a672']]
commandHashes={hashlib.sha256(json.dumps(c).encode()).hexdigest()for c in commands}
for path in (ROOT.parents[1]/'coordination/receipts').glob('*.json'):
    record=json.loads(path.read_text())
    if record.get('command_sha256')in commandHashes:copy(path,Path('guard-receipts')/path.name)
objects={}
for platform in ['macosx','iphoneos']:
    for name in ['NativeTransport.o','DecodeProbe.o']:
        path=ROOT/platform/name;objects[f'{platform}/{name}']={'sha256':digest(path),'bytes':path.stat().st_size}
old=json.loads((P0/'audio/evidence/artifact-manifest.json').read_text())
libraries={}
for name in ['libavformat','libavcodec','libavutil','libswresample']:
    path=ROOT/'decoder-inputs/lib'/(name+'.a');expected=old[f'macosx/{name}/{name}.a']['sha256'];assert digest(path)==expected
    libraries[name]={'sha256':digest(path),'verified_against_original_audio_manifest':True}
inventory=[]
for path in sorted(ROOT.iterdir()):
    files=[p for p in ([path]if path.is_file()else path.rglob('*'))if p.is_file()]
    inventory.append({'path':str(path),'logical_bytes':sum(p.stat().st_size for p in files),'allocated_bytes':sum(p.stat().st_blocks*512 for p in files)})
manifest={'source_hashes':{p.name:digest(p)for p in HERE.iterdir()if p.is_file()},
 'objects':objects,'verified_decoder_libraries':libraries,'selected_runs':{k:str(v)for k,v in selected.items()},
 'scratch':inventory,'scratch_cap_bytes':200*1024**2,'actual_free_bytes':shutil.disk_usage(ROOT).free,
 'cleanup':'Root coordinates stage-end; no deletion. Recovery Trash9,486,336 allocated bytes. No bytes recovered.'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
size=sum(p.stat().st_size for p in OUT.rglob('*')if p.is_file());assert size<1024*1024
print(json.dumps({'evidence_logical_bytes':size,'manifest_sha256':digest(OUT/'manifest.json'),'scratch_allocated_file_bytes':sum(x['allocated_bytes']for x in inventory)}))
