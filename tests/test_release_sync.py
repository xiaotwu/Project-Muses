import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sync', Path(__file__).parents[1] / 'scripts/sync-releases.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class ReleaseSyncTests(unittest.TestCase):
    def test_platform_tags_do_not_collide(self):
        self.assertNotEqual(sync.mirror_tag('erato', 'v1.0.0'), sync.mirror_tag('polyhymnia', 'v1.0.0'))

    def test_unsafe_assets_are_rejected(self):
        for name in ['../key', '/tmp/key', '..', 'a\\b', 'source-release.json', 'a\nb']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                sync.asset_name(name)

    def test_modified_or_truncated_download_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Muses.zip'
            path.write_bytes(b'original signed package')
            original = sync.digest_file(path)
            self.assertEqual(sync.verify_asset(path, {'size': path.stat().st_size, 'digest': original}), original)
            with self.assertRaises(ValueError):
                sync.verify_asset(path, {'size': path.stat().st_size + 1, 'digest': original})
            path.write_bytes(b'different signed package')
            with self.assertRaises(ValueError):
                sync.verify_asset(path, {'size': path.stat().st_size, 'digest': original})

    def test_unmanaged_release_is_not_overwritten(self):
        source = {'tag_name': 'v1', 'assets': [{'name': 'app.zip'}]}
        with self.assertRaises(ValueError):
            sync.sync('erato', source, {'erato/v1': {'body': 'Owner release notes'}}, plan=True)

    def test_draft_recovery_uses_release_id_and_keeps_verified_assets(self):
        asset = {'name': 'app.zip', 'size': 100, 'digest': 'sha256:abc'}
        source = {'tag_name': 'v1', 'assets': [asset], 'prerelease': False,
                  'html_url': 'https://github.com/xiaotwu/Muses-Polyhymnia/releases/tag/v1'}
        target = {'body': sync.MARKER, 'assets': [asset], 'prerelease': False, 'draft': True}
        def command(*args):
            return '{"databaseId": 123}' if args[:2] == ('release', 'view') else ''
        with patch.object(sync, 'gh', side_effect=command) as commands, \
             patch.object(sync, 'api', side_effect=[{'sha': 'source-sha'}, {'assets': [asset]}]) as requests, \
             patch.object(sync.subprocess, 'run') as download:
            sync.sync('polyhymnia', source, {'polyhymnia/v1': target})
        download.assert_not_called()
        self.assertEqual(requests.call_args_list[-1].args[0], 'repos/xiaotwu/Project-Muses/releases/123')
        self.assertTrue(any(call.args[:2] == ('release', 'edit') and '--draft=false' in call.args
                            for call in commands.call_args_list))

    def test_completed_mirror_is_idempotent_without_download(self):
        asset = {'name': 'app.zip', 'size': 100, 'digest': 'sha256:abc'}
        source = {'tag_name': 'v1', 'assets': [asset], 'prerelease': True}
        target = {'body': sync.MARKER, 'assets': [asset, {'name': 'source-release.json'}], 'prerelease': True, 'draft': False}
        sync.sync('erato', source, {'erato/v1': target})


if __name__ == '__main__':
    unittest.main()
