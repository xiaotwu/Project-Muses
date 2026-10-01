<p align="center"><img src="docs/assets/icon.png" width="88" alt="Muses icon"></p>
<h1 align="center">Project Muses</h1>
<p align="center">A native home for YouTube music. Three platforms, one family.</p>
<p align="center"><a href="https://xiaotwu.github.io/Project-Muses/">Website</a> · <a href="https://github.com/xiaotwu/Project-Muses/releases">Downloads & releases</a> · <a href="docs/installation.md">Installation</a></p>

**Polyhymnia is the core Muses product.** Erato and Euterpe adapt its library, artwork, queue and interaction principles to their platforms. The installed application is **Muses** on every platform. Each port has its own implementation, capabilities and release version. The [platform baseline](docs/platform-baseline.md) defines the shared direction; Windows may be rebuilt against Polyhymnia while preserving user data.

| Project | Platform | Status |
| --- | --- | --- |
| [Muses-Polyhymnia](https://github.com/xiaotwu/Muses-Polyhymnia) | macOS 14+ | Core native application; signed, notarized releases |
| [Muses-Erato](https://github.com/xiaotwu/Muses-Erato) | iOS 18+, iPhone/iPad | Beta; separate Public and experimental Native builds |
| [Muses-Euterpe](https://github.com/xiaotwu/Muses-Euterpe) | Windows 11 | Development; no published Windows, Store or WinGet package |

Public iOS uses a visible YouTube player and pauses in the background. Native is experimental and its Ad Hoc IPA requires provisioned devices or valid re-signing. Public IPAs use App Store distribution signing. GitHub releases do not establish Apple review or Google verification. Read the platform release notes before installing.

## Repository layout

```text
Project-Muses/
├── Muses-Polyhymnia/    # Independent Git submodule: macOS core
├── Muses-Erato/         # Independent Git submodule: iOS
├── Muses-Euterpe/       # Independent Git submodule: Windows 11
├── docs/               # Sole GitHub Pages website
├── scripts/            # Site validation and release aggregation
├── .github/workflows/  # Pages + release aggregation
└── README.md
```

```sh
git clone --recurse-submodules https://github.com/xiaotwu/Project-Muses.git
cd Project-Muses
# If already cloned without children:
git submodule update --init --recursive
```

Submodule commits are pinned for reproducibility. To edit a child, switch it to its working branch, commit changes there, merge and push its `main`, then commit the changed gitlink in Project-Muses. Do not commit platform files as ordinary files in the parent repository. Standalone clones of each platform remain supported.

## Website

Only this repository deploys [GitHub Pages](https://xiaotwu.github.io/Project-Muses/), through `.github/workflows/pages.yml`. The old Polyhymnia site has moved here. Erato's passive policy pages are published at `ios/` within the family site; its policy builder remains a local source/parity check.

The landing page keeps the existing Mac screenshot tour and adds platform descriptions and installation boundaries. Its hero/features/CTA structure takes inspiration from [Betchya/landingPage](https://github.com/Betchya/landingPage); no template code or artwork is copied. The site remains static HTML/CSS/JavaScript with Jekyll-rendered documentation.

```sh
python3 scripts/check-site.py
python3 scripts/sync-site-assets.py --check
# After approved platform policy or canonical-icon updates:
python3 scripts/sync-site-assets.py
# Local full render, if Jekyll is installed:
jekyll build --source docs --destination _site
python3 scripts/check-site.py --root _site --rendered
```

Keep screenshot captions aligned with the shipped UI. Platform-specific policies remain distinct; the iOS policy snapshot must match its in-app policy builder. Changes to Google Cloud consent URLs, Search Console and App Store Connect metadata require updates in those services separately.

## Releases

Build, sign, notarize and audit in the platform repository using its native toolchain. Publish the platform's original release there, then aggregate it here without rebuilding or changing its assets. Platform build pipelines and app update checks remain platform-owned; update checks must not mistake another platform's release for an app update.

- `polyhymnia/v0.5.6` — macOS version namespace.
- `erato/v1.0.0-beta.2` — iOS namespace; prerelease state and signing restrictions preserved.
- `euterpe/<source-tag>` — Windows namespace, once a release exists.

`.github/workflows/releases.yml` checks recent source releases hourly and can also be dispatched manually. The main repository's `GITHUB_TOKEN` can read public platform releases and write its own releases; no cross-repository write secret is needed. Uploaded assets are SHA256 verified; `source-release.json` records the source tag, resolved commit and asset digests. New mirrors stay drafts until every uploaded asset is verified. Existing published assets are not overwritten. Mirrors use `latest=false`; download by platform rather than a family-wide `/releases/latest`.

```sh
python3 -m unittest discover -s tests
python3 scripts/sync-releases.py --plan --count 1
python3 scripts/sync-releases.py --platform all --count 1
```

## Local workspace and Codex

The existing checkouts were physically moved under Project-Muses. Compatibility symlinks at their old `/Users/xiaotwu/Code/Muses-*` paths preserve existing Codex chat directories and build-cache references. These symlinks are outside Git and can be removed after saved projects/chats no longer depend on them. New work should use the nested paths. Codex project organization can be grouped in a Muses sidebar section; its available project tools do not migrate saved project paths or historical chat directories.

[MIT license](LICENSE). Third-party tools retain their own licenses.
