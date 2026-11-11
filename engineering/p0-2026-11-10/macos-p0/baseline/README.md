# macOS 0.6.3 baseline preparation

The official 0.6.3 / 20261105.1 application has been copied into a new isolated
acceptance identity, signed and verified. It has **not been launched or measured**.
No personal library, account, preferences or playback history was used as a seed.

The source ZIP SHA is
`192b4297c6dac82c5115afb1ba7168bae4e88985959a5852f85344df8b9b5a44`.
The original application passes strict nested signature verification and its main
executable matches the published checkpoint. The derivative preserves all 37
compiled Mach-O sections and all nested bundle bytes; only the root Info.plist,
main signature and root CodeResources change. This is a **metadata-isolated
derivative of 0.6.3**, not an assertion that the entire app bundle is byte-identical
to the public archive.

The new bundle is `com.muses.acceptance.p0-baseline-20261110`, named
`Muses P0 Baseline`. Its root URL schemes, OAuth client configuration, Web Home
and automatic updater configuration are disabled. Existing native acceptance
paths isolate application data, caches and resolver implicit configuration.
No runtime state has yet been created; [before-launch receipt](runtime-before.json).
The exact nested helper identities are retained in the
[preparation receipt](preparation-receipt.json) for later registration cleanup.

Preparation runs through the original disk guard and a frozen script/plan:

```sh
python3 engineering/p0-2026-11-10/run_guarded.py --allocation interop --timeout 120 -- python3 engineering/p0-2026-11-10/macos-p0/baseline/prepare.py plan
python3 engineering/p0-2026-11-10/run_guarded.py --allocation interop --timeout 180 -- python3 engineering/p0-2026-11-10/macos-p0/baseline/prepare.py prepare --plan-sha256 09136f9658308021ff57edc55e594087b0689dc35188b0f102519277b6721e82
```

These completed commands are evidence, not instructions to repeat over the
existing stage. The script refuses an existing stage for journal review.
Its SHA is `79aa6195393907ca11d5194e1018a7d657aad317aaf2f2b3cb1d2504b72fe872`;
the [journal](preparation-journal.jsonl) is complete with no failed step.
The prepared application is the single retained baseline under the 768 MiB
subbudget; the original archive and app remain unchanged in their prior location.

Before collecting a performance baseline, freeze the playable corpus and exact
attempt ordering, calibrate the real output measurement, create empty owned
runtime state and enforce its total cache budget. Launch through the app bundle
with a task-owned entry point, never by starting a SwiftUI GUI executable directly.
Playback resolution, file-loaded events or PCM submission alone are not
`t_sound`. No first-sound percentile, production improvement or 100-attempt
campaign is claimed by this preparation.
