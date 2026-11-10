#!/usr/bin/env python3
"""Copy only symbols/type from this subtask's exact local crash reports."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
scratch=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser')
reports=Path('/Users/xiaotwu/Library/Logs/DiagnosticReports')
rows=[]
for name in ('parser-proof-2026-11-10-135437.ips','quickjs-phase-2026-11-10-135615.ips'):
    path=reports/name
    if not path.exists():continue
    raw=path.read_text();report=json.loads(raw[raw.index('\n')+1:]);thread=report['threads'][report['faultingThread']]
    rows.append({'program':name.split('-2026-')[0],'exception_type':report.get('exception',{}).get('type'),'signal':report.get('exception',{}).get('signal'),'top_symbols':[{'symbol':f.get('symbol','unsymbolicated'),'offset':f.get('symbolLocation',0)} for f in thread.get('frames',[])[:8]]})
summary={'raw_report_copied':False,'private_identifiers_copied':False,'crashes':rows,'quickjs_diagnostic_note':'Full-parse diagnostic predates scoped structuredClone completion; runtime cause requires corrected-host reproduction. Original native window null-field fault was fixed and repeated malformed recovery now passes.'}
(scratch/'results/sanitized-crash-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
original=(root/'extract.js').read_text()
added="import * as Log from 'p0-upstream/utils/Log.js';\nLog.setLevel(Log.Level.NONE);\n// Meriyah uses this only to copy its plain Identifier/StringLiteral records.\n// Same scoped JSON clone as the frozen P0 shim, not a general Web API claim.\nglobalThis.structuredClone ??= value=>JSON.parse(JSON.stringify(value));\n"
assert added in original
old=original.replace(added,'',1)
evidence=root/'evidence';evidence.mkdir(exist_ok=True)
(evidence/'reproducer-pre-clone.js').write_text(old)
print(json.dumps({'sanitized_reports':len(rows),'reconstructed_pre_clone_source_sha256':hashlib.sha256(old.encode()).hexdigest(),'quickjs_phase_source_sha256':hashlib.sha256((root/'quickjs_phase.c').read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256((scratch/'build/quickjs-phase').read_bytes()).hexdigest()}))
