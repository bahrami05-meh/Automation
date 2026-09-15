# پروزه اتوماسیون بورسی
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('local_check', ROOT / 'check-local.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ConfigTests(unittest.TestCase):
    def validate(self, content):
        scratch = ROOT / 'tmp'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            file = Path(folder) / 'settings.toml'
            file.write_text(content, encoding='utf-8')
            return checker.load_config(file)

    def setUp(self):
        self.example = (ROOT / 'config.example.toml').read_text(encoding='utf-8')

    def test_valid_settings_resolve_to_project(self):
        _, paths = self.validate(self.example)
        self.assertEqual(paths['data'], ROOT / 'data')

    def test_parent_traversal_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(self.example.replace('data = "data"', 'data = "../outside"'))

    def test_public_bind_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(self.example.replace('127.0.0.1', '0.0.0.0'))

    def test_invalid_port_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(self.example.replace('8765', '70000'))


if __name__ == '__main__':
    unittest.main()
