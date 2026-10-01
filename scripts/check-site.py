#!/usr/bin/env python3
"""Validate static publication links, IDs, assets and platform content before deployment."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


class Audit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids = [], set()
        self.h1 = self.main = 0

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                raise ValueError(f'Duplicate ID: {attrs["id"]}')
            self.ids.add(attrs['id'])
        self.h1 += tag == 'h1'
        self.main += tag == 'main'
        for name in ('href', 'src'):
            if attrs.get(name):
                self.links.append(attrs[name])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default='docs')
    parser.add_argument('--rendered', action='store_true')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    pages = {}
    for path in root.rglob('*.html'):
        if any(part.startswith('_') for part in path.relative_to(root).parts):
            continue
        audit = Audit()
        audit.feed(path.read_text())
        if audit.h1 != 1 or audit.main != 1:
            raise ValueError(f'{path}: expected one h1 and one main')
        pages[path] = audit
    for path, audit in pages.items():
        for link in audit.links:
            if '{{' in link:
                continue
            url = urlsplit(link)
            if url.scheme or url.netloc:
                if 'xiaotwu.github.io/Muses/' in link or 'github.com/xiaotwu/Muses/' in link:
                    raise ValueError(f'{path}: retired project link: {link}')
                continue
            location = unquote(url.path)
            if location.startswith('/Project-Muses/'):
                target = root / location.removeprefix('/Project-Muses/')
            elif location.startswith('/'):
                target = root / location.lstrip('/')
            else:
                target = path.parent / location if location else path
            target = target.resolve()
            if not target.is_relative_to(root):
                raise ValueError(f'{path}: link outside publication root: {link}')
            if target.is_dir():
                target = target / 'index.html'
            if not target.exists():
                if not args.rendered and target.suffix == '.html' and target.with_suffix('.md').exists():
                    continue
                raise ValueError(f'{path}: missing link/resource: {link}')
            if url.fragment and target in pages and url.fragment not in pages[target].ids:
                raise ValueError(f'{path}: missing fragment: {link}')
    # Product-facing pages keep provider and tooling names out of their copy.
    forbidden = re.compile(r'youtube|google|chatgpt|codex', re.IGNORECASE)
    product_pages = [root / 'index.html', root / 'ios/index.html',
                     root / ('installation.html' if args.rendered else 'installation.md')]
    for product_page in product_pages:
        if forbidden.search(product_page.read_text()):
            raise ValueError(f'{product_page}: provider/tooling name in product copy')
    homepage = (root / 'index.html').read_text()
    for expected in ['Polyhymnia', 'Erato', 'Euterpe', 'macOS', 'iOS', 'Windows 11', 'role="tablist"', 'prefers-reduced-motion']:
        assert expected in homepage, f'Missing homepage contract: {expected}'
    # JavaScript tour assets are not HTML src attributes.
    for name in ['tour-home.png', 'tour-songs.png', 'tour-now-playing.jpg', 'tour-settings.jpg']:
        assert (root / 'assets' / name).is_file(), f'Missing screenshot: {name}'
    assert 'https://xiaotwu.github.io/Project-Muses/' in homepage
    print(f'PASS: {len(pages)} HTML pages; local links, resources, fragments and platform content.')


if __name__ == '__main__':
    main()
