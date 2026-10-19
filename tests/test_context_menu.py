from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]

class ContextMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import gi
        try: gi.require_version('Nautilus', '4.0')
        except ValueError: raise unittest.SkipTest('python3-nautilus not installed')
        cls.extension = ModuleType('converto_extension_test')
        text = (ROOT/'integrations/converto-nautilus.py.in').read_text()
        exec(compile(text.replace('__CONVERTO_LAUNCHER__', repr(str(ROOT/'run.sh'))), '<extension>', 'exec'), cls.extension.__dict__)

    def file(self, uri): return SimpleNamespace(get_uri=lambda: uri)

    def test_top_level_convert_and_exact_batch_paths(self):
        files = [self.file(Path('/tmp/photo with spaces.png').as_uri()),
                 self.file(Path('/tmp/line\nbreak;$(touch nope).jpg').as_uri())]
        provider = self.extension.ConvertoMenuProvider()
        items = provider.get_file_items(files)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].props.label, 'Convert')
        with patch.object(self.extension.Gio.Subprocess, 'new') as launch:
            items[0].activate()
            self.assertEqual(launch.call_args.args[0], [str(ROOT/'run.sh'), '--',
                '/tmp/photo with spaces.png', '/tmp/line\nbreak;$(touch nope).jpg'])

    def test_empty_and_remote_selections(self):
        provider = self.extension.ConvertoMenuProvider()
        self.assertEqual(provider.get_file_items([]), [])
        self.assertEqual(provider.get_file_items([self.file('smb://server/photo.png')]), [])
        self.assertEqual(provider.get_file_items([self.file('file:///tmp/photo.png'), self.file('https://example.com/p.png')]), [])

    def test_folder_available(self):
        self.assertEqual(len(self.extension.ConvertoMenuProvider().get_file_items([self.file('file:///tmp')])), 1)

if __name__ == '__main__': unittest.main()
