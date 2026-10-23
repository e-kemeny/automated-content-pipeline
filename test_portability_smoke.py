"""Mocked orchestration and real guard checks; no encoding in unit tests."""
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import portability_smoke as smoke


class PortabilitySmokeTests(unittest.TestCase):
    def test_command(self):
        command = smoke.pipeline_command('a video.mp4', 'a.json', 'new output', True)
        self.assertEqual(command[:4], [smoke.sys.executable, '-B', '-S', '-c'])
        self.assertEqual(command[-8:], ['a.json', '--mode', 'both', '--manifest-version',
                                       '2', '--output-root', 'new output', '--cache-only'])
        self.assertNotIn('--force', command)
        self.assertNotIn('--cache-only', smoke.pipeline_command('v', 'a', 'o'))

    def test_success_and_rejection(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            for code, text, rejection in ((0, 'Shorts: success\nLong-form: success', None),
                    (1, 'Shorts: failed\nLong-form: failed\nSource identity mismatch',
                     'Source identity mismatch')):
                with patch.object(smoke.subprocess, 'run', return_value=
                        subprocess.CompletedProcess([], code, text, '')) as run:
                    smoke.invoke(root, 'v', 'a', 'o', cache_only=True, rejection=rejection)
                    self.assertEqual(run.call_args.kwargs['cwd'], root)

    def test_failed_or_partial_subprocess(self):
        with tempfile.TemporaryDirectory() as work:
            for code in (0, 1):
                with patch.object(smoke.subprocess, 'run', return_value=
                        subprocess.CompletedProcess([], code, 'Shorts: success', 'problem')):
                    with self.assertRaisesRegex(ValueError, 'Both exporters'):
                        smoke.invoke(Path(work), 'v', 'a', 'o')

    def test_changed_hash_mtime_and_addition(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            path = root/'artifact'
            path.write_bytes(b'original')
            for mode in ('bytes', 'mtime', 'addition'):
                def run(*args, **kwargs):
                    if mode == 'bytes': path.write_bytes(b'changed')
                    elif mode == 'mtime':
                        import os
                        stat = path.stat()
                        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns+10000000))
                    else: (root/'unexpected').mkdir()
                    return subprocess.CompletedProcess([], 0, 'Shorts: success\nLong-form: success', '')
                with patch.object(smoke.subprocess, 'run', side_effect=run):
                    with self.assertRaisesRegex(ValueError, 'changed fixture'):
                        smoke.invoke(root, 'v', 'a', 'o', cache_only=True)

    def test_orchestration_relocates_and_cleans_only_owned_subtree(self):
        with tempfile.TemporaryDirectory() as work:
            parent = Path(work)
            sentinel = parent/'keep'
            sentinel.write_bytes(b'untouched')
            def create(root):
                root.mkdir()
                (root/'synthetic.mp4').write_bytes(b'fixture')
                (root/'analysis.json').write_text('{}')
                output = root/'portable exports'
                output.mkdir()
                for index in range(6): (output/f'{index}.mp4').write_bytes(b'clip')
                for index in range(2): (output/f'{index}_manifest.json').write_text('{}')
            with patch.object(smoke, 'create_fixture', side_effect=create), \
                 patch.object(smoke, 'invoke') as invoke, \
                 patch.object(smoke.shutil, 'which', return_value='tool'), \
                 contextlib.redirect_stdout(io.StringIO()):
                smoke.smoke(parent)
            self.assertEqual(invoke.call_count, 5)
            self.assertFalse(invoke.call_args_list[0].kwargs.get('cache_only', False))
            self.assertTrue(all(c.kwargs['cache_only'] for c in invoke.call_args_list[1:]))
            self.assertIn('relocated workspace', str(invoke.call_args_list[2].args[0]))
            self.assertEqual(invoke.call_args_list[-1].kwargs['rejection'], 'Media file not found')
            self.assertEqual(list(parent.iterdir()), [sentinel])
            self.assertEqual(sentinel.read_bytes(), b'untouched')

    def test_missing_tool_and_exit_codes(self):
        with patch.object(smoke.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(ValueError, 'Missing ffmpeg'):
                smoke.smoke(smoke.ROOT)
        with patch.object(smoke, 'smoke') as run:
            self.assertEqual(smoke.main([]), 0)
            run.side_effect = ValueError('fixture failure')
            with contextlib.redirect_stderr(io.StringIO()) as out:
                self.assertEqual(smoke.main([]), 1)
            self.assertIn('FAIL', out.getvalue())

    def test_cleanup_on_failure(self):
        with tempfile.TemporaryDirectory() as work:
            with patch.object(smoke.shutil, 'which', return_value='tool'), \
                 patch.object(smoke, 'create_fixture', side_effect=ValueError('failed')):
                with self.assertRaises(ValueError): smoke.smoke(Path(work))
            self.assertEqual(list(Path(work).iterdir()), [])

    def test_real_child_guards_block_writes_encoding_and_models(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            for statement in ("open('forbidden', 'w')", "import torch",
                              "import subprocess; subprocess.run(['ffmpeg', '-version'])"):
                (root/'pipeline.py').write_text(statement)
                result = subprocess.run(smoke.pipeline_command('v', 'a', 'o', True),
                                        cwd=root, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('RuntimeError:', result.stderr)
                self.assertNotIn('TypeError:', result.stderr)
                self.assertFalse((root/'forbidden').exists())
            self.assertFalse((root/'__pycache__').exists())


if __name__ == '__main__':
    unittest.main()
