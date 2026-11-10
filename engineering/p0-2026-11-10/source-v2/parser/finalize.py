#!/usr/bin/env python3
"""Collect only bounded sanitized evidence; never copy player/media/private logs."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parent
SCRATCH=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser')
DEPS=SCRATCH.parent/'v2-integration/deps/node_modules'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
evidence=ROOT/'evidence';evidence.mkdir(exist_ok=True)
for f in sorted((SCRATCH/'results').glob('*.json')):
    raw=f.read_bytes();assert len(raw)<=65536 and b'googlevideo.com' not in raw and b'visitorData' not in raw
    json.loads(raw);shutil.copyfile(f,evidence/f.name)
notices=ROOT/'notices';notices.mkdir(exist_ok=True)
for name,path in {
    'tree-sitter-MIT.txt':SCRATCH/'tree-sitter/LICENSE',
    'tree-sitter-javascript-MIT.txt':SCRATCH/'tree-sitter-javascript/LICENSE',
    'youtubei-MIT.txt':DEPS/'youtubei.js/LICENSE',
    'meriyah-ISC.txt':DEPS/'meriyah/LICENSE.md',
    'quickjs-MIT.txt':SCRATCH.parent/'quickjs-2026-06-04/LICENSE',
}.items():shutil.copyfile(path,notices/name)
artifacts=[]
for rel in ('fixtures/player.js','fixtures/reduced.js','fixtures/reduced-reviewed.js','fixtures/solver.js','fixtures/reference-solver.js','build/extract.bundle.js','build/parser-proof','build/parser-tests','build/p0_parser.o','build/tree-sitter.o','build/javascript.o','build/scanner.o','build/iphoneos/libp0parser.a','build/quickjs-phase','build/jsc-reference'):
    p=SCRATCH/rel
    if p.exists():artifacts.append({'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)})
source_files=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name!='manifest.json']
upstream=[]
for rel in ('youtubei.js/dist/src/core/Player.js','youtubei.js/dist/src/utils/javascript/JsAnalyzer.js','youtubei.js/dist/src/utils/javascript/JsExtractor.js','youtubei.js/dist/src/utils/javascript/matchers.js','meriyah/dist/meriyah.mjs'):
    p=DEPS/rel;upstream.append({'path':rel,'sha256':sha(p)})
inventory=[]
for p in sorted(SCRATCH.iterdir()):
    files=[p]+list(p.rglob('*')) if p.is_dir() else [p]
    inventory.append({'path':str(p),'allocated_bytes':sum(f.lstat().st_blocks*512 for f in files),'logical_file_bytes':sum(f.stat().st_size for f in files if f.is_file()),'ownership':'p0_source parser subtask','retention':'active integration/reproduction; root coordinates recoverable cleanup'})
handles=subprocess.run(['lsof','+D',str(SCRATCH)],capture_output=True,text=True)
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'parser-only cold extraction; media/device gates not claimed','source_files':source_files,'artifacts':artifacts,'upstream_sources':upstream,'bootstrap':json.loads((SCRATCH/'results/bootstrap.json').read_text()),'scratch':{'root':str(SCRATCH),'subbudget_bytes':400*1024*1024,'allocated_bytes':sum(r['allocated_bytes'] for r in inventory),'logical_file_bytes':sum(r['logical_file_bytes'] for r in inventory),'free_bytes':shutil.disk_usage(SCRATCH).free,'inventory':inventory,'open_file_lines':len(handles.stdout.splitlines()),'lsof_exit_code':handles.returncode,'cleanup_performed':False,'bytes_recovered':0},'solver_reference_identical':(SCRATCH/'fixtures/solver.js').read_bytes()==(SCRATCH/'fixtures/reference-solver.js').read_bytes(),'no_signed_urls_headers_cookies_media_or_private_crash_logs_copied':True}
(ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'source_files':len(source_files),'receipts':len(list(evidence.glob('*.json'))),'solver_reference_identical':manifest['solver_reference_identical'],'scratch':{k:v for k,v in manifest['scratch'].items() if k!='inventory'},'manifest_sha256':sha(ROOT/'manifest.json')},indent=2))
