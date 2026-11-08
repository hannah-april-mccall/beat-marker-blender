import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('beat_marker_runtime', ROOT / 'beat_marker/runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='Beat Marker runtime test ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / 'extension/runtime'
        self.root.mkdir(parents=True)
        self.info = {'version': runtime.VERSION, 'platform': runtime.platform_key(), 'build_id': 'test-build',
                     'engine': 'engine/worker', 'ffmpeg': 'bin/ffmpeg', 'ffprobe': 'bin/ffprobe', 'model': 'model.ckpt'}
        for name in ('engine', 'ffmpeg', 'ffprobe', 'model'):
            path = self.root / self.info[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('test resource')
            path.chmod(0o600)
        self.save()

    def save(self):
        (self.root / 'runtime.json').write_text(json.dumps(self.info))

    def test_complete_matching_release(self):
        _, paths = runtime.validate(self.root)
        self.assertEqual(paths['model'], self.root / 'model.ckpt')

    def test_wrong_platform_explains_correct_download(self):
        self.info['platform'] = 'not-this-computer'; self.save()
        with self.assertRaisesRegex(ValueError, 'Install the release for'):
            runtime.validate(self.root)

    def test_old_worker_is_not_used_with_new_addon(self):
        self.info['version'] = '0.1.0'; self.save()
        with self.assertRaisesRegex(ValueError, 'version does not match'):
            runtime.validate(self.root)

    def test_missing_model_is_an_installation_error(self):
        (self.root / 'model.ckpt').unlink()
        with self.assertRaisesRegex(ValueError, 'incomplete: model'):
            runtime.validate(self.root)

    def test_manifest_cannot_reference_a_program_outside_the_bundle(self):
        outside = self.root.parent / 'outside'; outside.write_text('outside')
        self.info['engine'] = '../outside'; self.save()
        with self.assertRaisesRegex(ValueError, 'incomplete: engine'):
            runtime.validate(self.root)

    @unittest.skipIf(os.name == 'nt', 'Windows does not require Unix executable bits')
    def test_discarded_zip_permissions_are_repaired_outside_install(self):
        state = Path(self.temporary.name) / 'user data'
        copied, paths = runtime.prepare(state, self.root)
        self.assertTrue(copied.is_relative_to(state))
        self.assertTrue(all(os.access(paths[key], os.X_OK) for key in ('engine', 'ffmpeg', 'ffprobe')))
        self.assertFalse(os.access(self.root / self.info['engine'], os.X_OK))
        self.assertEqual(runtime.prepare(state, self.root)[0], copied)

    def test_blender_library_environment_is_not_inherited(self):
        with patch.dict(os.environ, {'PYTHONPATH': 'blender-libraries', 'LD_LIBRARY_PATH': 'blender-native-libraries'}):
            cleaned = runtime.process_environment()
        self.assertNotIn('PYTHONPATH', cleaned)
        self.assertNotIn('LD_LIBRARY_PATH', cleaned)


if __name__ == '__main__':
    unittest.main()
