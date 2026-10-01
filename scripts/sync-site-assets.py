#!/usr/bin/env python3
"""Refresh platform-owned public assets in the sole family website."""
import argparse
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--check', action='store_true', help='Validate policy/icon parity without changing the site')
args = parser.parse_args()
ios = root / 'Muses-Erato'
subprocess.run(['python3', str(ios / 'scripts/build-privacy-site.py'), '--check'], check=True)
pairs = [(ios / 'docs/site' / name, root / 'docs/ios' / name)
         for name in ['index.html', 'privacy.html', 'terms.html', 'styles.css', '.nojekyll']]
pairs.append((root / 'Muses-Polyhymnia/assets/icon.png', root / 'docs/assets/icon.png'))
for source, destination in pairs:
    if args.check:
        if source.read_bytes() != destination.read_bytes():
            raise SystemExit(f'Publication snapshot differs: {destination.relative_to(root)}')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
print('PASS: iOS policy output and macOS canonical icon match the family website.')
