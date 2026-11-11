#!/usr/bin/env python3
"""Prepare locked local package; suppress upstream logging of private stream data."""
import hashlib,json
from pathlib import Path
s=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source')
rev='7f75a2299dc329c0b7855afb25d47663a02855cb'
repo=s/f'YouTubeKit-{rev}'
manifest=s/'youtubekit-probe/Package.swift'
manifest.write_text('''// swift-tools-version:5.9
import PackageDescription
let package=Package(name:"SourceAlternativeProbe",platforms:[.macOS(.v13)],dependencies:[.package(path:"../YouTubeKit-'''+rev+'''")],targets:[.executableTarget(name:"Probe",dependencies:[.product(name:"YouTubeKit",package:"YouTubeKit-'''+rev+'''")])])
''')
provenance=s/'results/youtubekit-provenance.json'
changes=json.loads(provenance.read_text()).get('patches',[]) if provenance.exists() else []
for f in (repo/'Sources').rglob('*.swift'):
    text=f.read_text()
    if 'os_log(' in text:
        updated=text.replace('os_log(','p0_no_log(')
        changes.append({'path':str(f.relative_to(repo)),'upstream_sha256':hashlib.sha256(text.encode()).hexdigest(),'patched_sha256':hashlib.sha256(updated.encode()).hexdigest(),'change':'rename os_log to no-op; no extraction/network behavior changes'})
        f.write_text(updated)
logger=repo/'Sources/YouTubeKit/P0NoLog.swift'
logger.write_text('import os.log\nfunc p0_no_log(_ format:StaticString, dso:UnsafeRawPointer = #dsohandle, log:OSLog = .default, type:OSLogType = .default, _ args:CVarArg...) {}\n')
provenance.write_text(json.dumps({'commit':rev,'patches':changes,'license':'MIT','bundled_helper_license':'Unlicense','remote_fallback_used':False},indent=2)+'\n')
