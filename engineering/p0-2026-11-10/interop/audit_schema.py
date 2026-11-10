#!/usr/bin/env python3
"""Inventory model declarations from a pinned read-only source tree.

This is an inventory generator, not a Swift parser or a database migration.
Every model's stored declarations occur before its initializer in the audited
revision. The explicit expected model list makes omissions fail closed.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/Users/xiaotwu/Code/Project-Muses/Muses-Polyhymnia')
OUT = Path(__file__).resolve().parent
SCHEMA = ROOT / 'Sources/Muses/Persistence/MusesSchema.swift'
expected = re.findall(r'^        (\w+)\.self,', SCHEMA.read_text(), re.M)
tables = {
    'Track': 'library_track', 'QueueState': 'queue_checkpoint',
    'EQPreset': 'eq_preset', 'YouTubeImport': 'playlist_import',
    'YouTubeImportItem': 'import_occurrence', 'Playlist': 'playlist',
    'PlaylistItem': 'playlist_occurrence', 'ListeningEvent': 'listening_event',
    'ListeningSession': 'listening_session', 'TrackNote': 'track_note',
    'TrackBookmark': 'track_bookmark', 'CatalogRelease': 'catalog_release_cache',
    'CatalogArtist': 'catalog_artist_cache',
    'CatalogTrackReleaseMembership': 'track_release_evidence',
    'YouTubePlaylistRevision': 'playlist_revision', 'YouTubeSyncOperation': 'sync_operation',
    'YouTubeSyncBatch': 'sync_batch', 'YouTubePlaylistResourceOperation': 'playlist_resource_operation',
    'PodcastShow': 'podcast_follow', 'PodcastEpisodeState': 'podcast_episode_state',
    'PodcastEpisodeMembership': 'podcast_episode_membership',
}
overrides = {
    ('Track', 'youTubeImportItems'): 'inverse: import_occurrence.track_id',
    ('Track', 'youTubeId'): 'source_item_id',
    ('Playlist', 'items'): 'inverse: playlist_occurrence.playlist_id',
    ('PlaylistItem', 'playlist'): 'playlist_id', ('PlaylistItem', 'track'): 'track_id',
    ('YouTubeImport', 'items'): 'inverse: import_occurrence.import_id',
    ('YouTubeImportItem', 'import_'): 'import_id', ('YouTubeImportItem', 'track'): 'track_id',
    ('YouTubeImportItem', 'youTubeId'): 'source_item_id',
    ('TrackBookmark', 'timestampMs'): 'position_seconds',
}
def snake(name):
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()

models = {}
sources = {}
for path in sorted((ROOT / 'Sources/Muses/Domain').glob('*.swift')):
    source = path.read_text()
    for model in re.finditer(r'@Model\s+final class (\w+)\s*\{', source):
        name = model.group(1)
        if name not in expected:
            raise ValueError('unreviewed persistent model ' + name)
        body = source[model.end():]
        body = body[:re.search(r'\n    init\s*\(', body).start()]
        fields = []
        for match in re.finditer(r'^    (?:@Attribute\([^\n]*\) )?var (\w+): ([^\n]+)', body, re.M):
            field, declared = match.groups()
            if '{' in declared:
                continue
            declared = declared.split('//')[0].strip()
            fields.append({
                'source': field, 'swift_type': declared,
                'nullable': declared.endswith('?'),
                'target': overrides.get((name, field), snake(field)),
                'line': source[:model.end() + match.start()].count('\n') + 1,
            })
        relative = str(path.relative_to(ROOT))
        models[name] = {'table': tables[name], 'source': relative, 'fields': fields,
                        'category': 'rebuildable_cache' if name in ('CatalogRelease', 'CatalogArtist') else 'preserved_user_state_or_evidence'}
        sources[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
if set(models) != set(expected):
    raise ValueError('schema model inventory incomplete')
extra = [
    'Sources/Muses/Persistence/MusesSchema.swift',
    'Sources/Muses/Persistence/StoreUpgradeSnapshot.swift',
    'Sources/Muses/Domain/QueueItem.swift', 'Sources/Muses/Domain/QueueGroup.swift',
    'Sources/Muses/Domain/SmartShuffleState.swift', 'Sources/Muses/Domain/UserPreferences.swift',
    'Sources/Muses/Services/Queue/QueueService.swift',
    'Sources/Muses/Services/Notes/NotesService.swift',
    'Sources/Muses/Features/Notes/NotesSheets.swift',
    'Tests/MusesTests/NotesFeatureTests.swift',
]
for relative in extra:
    sources[relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
manifest = {
    'schema_generation': 7,
    'source_repository': 'xiaotwu/Muses-Polyhymnia',
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'status': 'read-only source inventory; proposed logical mapping; no user store read or migration performed',
    'models': {name: models[name] for name in expected}, 'source_sha256': sources,
}
(OUT / 'generation7-field-map.json').write_text(json.dumps(manifest, indent=2) + '\n')
lines = ['# Generation-7 field inventory', '', 'Generated from source by `audit_schema.py`. This lists declared stored properties, including inverse relationships; it is not a count of SQLite columns. SQL table/column names below are a proposed logical mapping for P1, not a completed migration.', '',
         '| Model / logical target | Source fields → target columns or relationships |', '| --- | --- |']
for name in expected:
    model = models[name]
    fields = '; '.join('`' + f['source'] + '` (' + f['swift_type'] + ') → `' + f['target'] + '`' for f in model['fields'])
    lines.append('| `' + name + '` → `' + model['table'] + '` | ' + fields + ' |')
(OUT / 'generation7-field-map.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({'models': len(models), 'stored_declarations_including_relationships': sum(len(m['fields']) for m in models.values()), 'source_files_hashed': len(sources), 'source_commit': manifest['source_commit']}))
