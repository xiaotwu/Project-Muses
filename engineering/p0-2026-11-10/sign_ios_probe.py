#!/usr/bin/env python3
"""Sign an isolated P0 candidate with an existing development profile.

No Developer Portal operations, installation, keychain edits or publication.
Run through run_guarded.py. Profile and signed bundle stay in private scratch.
"""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess

p = argparse.ArgumentParser()
p.add_argument('--candidate', type=Path, required=True)
p.add_argument('--destination', type=Path, required=True)
p.add_argument('--binary-sha256', required=True)
p.add_argument('--profile', type=Path, required=True)
p.add_argument('--identity', required=True)
p.add_argument('--device', required=True)
a = p.parse_args()
info = plistlib.loads((a.candidate / 'Info.plist').read_bytes())
assert info['CFBundleIdentifier'] == 'org.muses.p0.sourceprobe'
binary = a.candidate / info['CFBundleExecutable']
assert hashlib.sha256(binary.read_bytes()).hexdigest() == a.binary_sha256
assert not a.destination.exists(), 'Keep earlier signing attempts intact'
profile = plistlib.loads(subprocess.check_output(['security', 'cms', '-D', '-i', str(a.profile)]))
assert a.device in profile['ProvisionedDevices']
team = profile['TeamIdentifier'][0]
app_id = team + '.' + info['CFBundleIdentifier']
allowed = profile['Entitlements']['application-identifier']
assert allowed == app_id or allowed == team + '.*'
assert profile['Entitlements']['get-task-allow'] is True
entitlements = {'application-identifier': app_id,
                'com.apple.developer.team-identifier': team,
                'get-task-allow': True}
a.destination.parent.mkdir(parents=True, exist_ok=True)
ent = a.destination.parent / (a.destination.stem + '-entitlements.plist')
assert not ent.exists()
ent.write_bytes(plistlib.dumps(entitlements))
shutil.copytree(a.candidate, a.destination, symlinks=False)
shutil.copy2(a.profile, a.destination / 'embedded.mobileprovision')
subprocess.run(['codesign', '--force', '--sign', a.identity, '--entitlements', str(ent),
                '--generate-entitlement-der', str(a.destination)], check=True)
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(a.destination)], check=True)
receipt = {'bundle': info['CFBundleIdentifier'], 'unsigned_binary_sha256': a.binary_sha256,
           'signed_binary_sha256': hashlib.sha256((a.destination / info['CFBundleExecutable']).read_bytes()).hexdigest(),
           'entitlements_sha256': hashlib.sha256(ent.read_bytes()).hexdigest(),
           'existing_profile': True, 'new_portal_registration': False,
           'signature_verify': 'passed'}
(a.destination.parent / (a.destination.stem + '-signing.json')).write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
