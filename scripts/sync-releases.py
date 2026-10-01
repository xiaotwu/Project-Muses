#!/usr/bin/env python3
"""Mirror published platform releases and verified assets into the family repository."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote

SOURCES = {
    'polyhymnia': 'xiaotwu/Muses-Polyhymnia',
    'erato': 'xiaotwu/Muses-Erato',
    'euterpe': 'xiaotwu/Muses-Euterpe',
}
DESTINATION = 'xiaotwu/Project-Muses'
MARKER = '<!-- project-muses-release-mirror -->'


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True)


def api(path):
    return json.loads(gh('api', path))


def releases(repo):
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{repo}/releases?per_page=100'))
    return [release for page in pages for release in page if not release['draft']]


def mirror_tag(platform, tag):
    if platform not in SOURCES or not tag or any(c in tag for c in '\r\n'):
        raise ValueError('Invalid platform or source tag')
    return f'{platform}/{tag}'


def asset_name(name):
    if not name or name in {'.', '..', 'source-release.json'} or Path(name).name != name or '\\' in name or any(ord(c) < 32 for c in name):
        raise ValueError(f'Unsafe or reserved asset name: {name!r}')
    return name


def digest_file(path):
    with path.open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_asset(path, source):
    if path.stat().st_size != source['size']:
        raise ValueError(f'Asset size mismatch: {path.name}')
    digest = digest_file(path)
    if source.get('digest') and source['digest'] != digest:
        raise ValueError(f'Asset SHA256 mismatch: {path.name}')
    return digest


def sync(platform, source, existing, plan=False):
    repo = SOURCES[platform]
    tag = mirror_tag(platform, source['tag_name'])
    assets = source['assets']
    if not assets:
        print(f'SKIP {repo} {source["tag_name"]}: no published build assets')
        return
    if len({asset_name(a['name']) for a in assets}) != len(assets):
        raise ValueError('Duplicate source asset names')
    target = existing.get(tag)
    if target and MARKER not in (target.get('body') or ''):
        raise ValueError(f'Refusing to replace an unmanaged release: {tag}')
    target_assets = {a['name']: a for a in target['assets']} if target else {}
    def matches(a):
        b = target_assets.get(a['name'])
        return b and a.get('digest') and a['digest'] == b.get('digest') and a['size'] == b['size']
    if target and not target['draft'] and all(matches(a) for a in assets) and 'source-release.json' in target_assets and target['prerelease'] == source['prerelease']:
        print(f'UNCHANGED {tag}')
        return
    print(f'{"PLAN" if plan else "SYNC"} {repo} {source["tag_name"]} -> {tag} ({len(assets)} assets)')
    if plan:
        return
    # Resolve the source tag rather than relying on target_commitish, which may be a branch.
    commit = api(f'repos/{repo}/commits/{quote(source["tag_name"], safe="")}')['sha']
    with tempfile.TemporaryDirectory(prefix='muses-release-') as directory:
        temp = Path(directory)
        manifest = {'source_repository': repo, 'source_release': source['html_url'],
                    'source_tag': source['tag_name'], 'source_commit': commit,
                    'prerelease': source['prerelease'], 'assets': []}
        for asset in assets:
            name = asset_name(asset['name'])
            if matches(asset):
                manifest['assets'].append({'name': name, 'size': asset['size'], 'digest': asset['digest']})
                continue
            path = temp / name
            # Download exact assets through their numeric API IDs; names are not glob patterns.
            with path.open('wb') as output:
                subprocess.run(['gh', 'api', '-H', 'Accept: application/octet-stream',
                                f'repos/{repo}/releases/assets/{asset["id"]}'], stdout=output, check=True)
            digest = verify_asset(path, asset)
            manifest['assets'].append({'name': name, 'size': asset['size'], 'digest': digest})
            if name in target_assets and target_assets[name].get('digest') != digest:
                raise ValueError(f'Refusing to overwrite changed published asset: {tag}/{name}')
        notes = temp / 'release-notes.md'
        notes.write_text(f'{MARKER}\nBuilt and published in [{repo}]({source["html_url"]}). '
                         f'Source tag `{source["tag_name"]}`, commit `{commit}`. '
                         'Assets are copied byte-for-byte; platform signing and installation restrictions remain unchanged.\n\n'
                         + (source.get('body') or ''), encoding='utf-8')
        provenance = temp / 'source-release.json'
        provenance.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        if not target:
            gh('release', 'create', tag, '--repo', DESTINATION, '--target', 'main', '--draft',
               '--title', source.get('name') or tag, '--notes-file', str(notes))
        for asset in assets:
            if asset['name'] not in target_assets:
                gh('release', 'upload', tag, str(temp / asset['name']), '--repo', DESTINATION)
        # The generated provenance may change when a source release gains an asset.
        gh('release', 'upload', tag, str(provenance), '--repo', DESTINATION, '--clobber')
        # Draft releases have no published tag ref; GitHub's by-tag API returns 404.
        release_id = json.loads(gh('release', 'view', tag, '--repo', DESTINATION, '--json', 'databaseId'))['databaseId']
        uploaded = api(f'repos/{DESTINATION}/releases/{release_id}')
        remote_assets = {a['name']: a for a in uploaded['assets']}
        for a in manifest['assets']:
            b = remote_assets[a['name']]
            if b['size'] != a['size'] or b.get('digest') != a['digest']:
                raise ValueError(f'Mirrored asset verification failed: {tag}/{a["name"]}')
        gh('release', 'edit', tag, '--repo', DESTINATION, '--draft=false', '--latest=false',
           f'--prerelease={str(source["prerelease"]).lower()}',
           '--title', source.get('name') or tag, '--notes-file', str(notes))
        print(f'PUBLISHED https://github.com/{DESTINATION}/releases/tag/{quote(tag, safe="")}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=[*SOURCES, 'all'], default='all')
    parser.add_argument('--count', type=int, default=1, help='Recent releases per platform to examine')
    parser.add_argument('--plan', action='store_true', help='Read metadata without downloading or publishing')
    args = parser.parse_args()
    if not 1 <= args.count <= 100:
        parser.error('--count must be between 1 and 100')
    # Include drafts for interrupted upload recovery.
    pages = json.loads(gh('api', '--paginate', '--slurp', f'repos/{DESTINATION}/releases?per_page=100'))
    existing = {r['tag_name']: r for page in pages for r in page}
    for platform in SOURCES if args.platform == 'all' else [args.platform]:
        candidates = releases(SOURCES[platform])[:args.count]
        if not candidates:
            print(f'NO RELEASES {SOURCES[platform]}')
        for source in reversed(candidates):
            sync(platform, source, existing, args.plan)


if __name__ == '__main__':
    main()
