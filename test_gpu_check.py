"""GPU diagnostics tested entirely with mocked NVIDIA subprocess responses."""
import contextlib
import io
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import gpu_check as check

GPU = '<gpu id="fixture"><product_name>Fixture GPU</product_name><fb_memory_usage><free>123.5 MiB</free><total>1024 MiB</total></fb_memory_usage></gpu>'


def xml(gpus=GPU, count=1, versions='<driver_version>123.45</driver_version><cuda_version>12.0</cuda_version>'):
    return f'<nvidia_smi_log>{versions}<attached_gpus>{count}</attached_gpus>{gpus}</nvidia_smi_log>'


class GPUCheckTests(unittest.TestCase):
    def query(self, stdout='', stderr='', code=0, error=None):
        with patch.object(check.shutil, 'which', return_value='tools/nvidia-smi'), \
             patch.object(check.subprocess, 'run', side_effect=error,
                          return_value=SimpleNamespace(stdout=stdout,stderr=stderr,returncode=code)) as run:
            report=check.inspect_gpu()
        run.assert_called_once_with(['tools/nvidia-smi','-q','-x'],capture_output=True,
                                    text=True,check=False,timeout=10)
        return report

    def test_single_gpu_and_command(self):
        report=self.query(xml())
        self.assertEqual(report['hardware'],'DETECTED')
        self.assertEqual(report['driver'],'AVAILABLE')
        self.assertEqual(report['driver_version'],'123.45')
        self.assertEqual(report['cuda_reported'],'12.0')
        self.assertEqual(report['gpus'][0]['free_memory'],'123.5 MiB')
        self.assertEqual(report['exit_code'],0)

    def test_multiple_gpus(self):
        report=self.query(xml(GPU+GPU.replace('Fixture GPU','Second GPU'),2))
        self.assertEqual([g['name'] for g in report['gpus']],['Fixture GPU','Second GPU'])
        self.assertEqual([g['index'] for g in report['gpus']],[0,1])

    def test_no_gpu(self):
        report=self.query(xml('',0))
        self.assertEqual(report['hardware'],'NOT DETECTED')
        self.assertEqual(report['driver'],'AVAILABLE')
        report=self.query('No devices were found\n',code=6)
        self.assertEqual(report['hardware'],'NOT DETECTED')
        self.assertEqual(report['driver'],'UNVERIFIED')
        self.assertEqual(report['exit_code'],0)

    def test_missing_executable(self):
        with patch.object(check.shutil,'which',return_value=None), patch.object(check.subprocess,'run') as run:
            report=check.inspect_gpu()
        run.assert_not_called()
        self.assertEqual(report['hardware'],'UNVERIFIED')
        self.assertEqual(report['exit_code'],1)

    def test_timeout_and_os_failure(self):
        for error in (subprocess.TimeoutExpired([],10),OSError('cannot execute'),UnicodeError('decode')):
            report=self.query(error=error)
            self.assertEqual(report['exit_code'],1)
            self.assertEqual(report['driver'],'UNVERIFIED')

    def test_driver_failure(self):
        report=self.query(stderr='Failed to communicate with the NVIDIA driver',code=9)
        self.assertEqual(report['hardware'],'UNVERIFIED')
        self.assertIn('exit 9',report['error'])

    def test_malformed_output(self):
        for text in ('', '<bad>', '<other/>', xml(count=2), xml(versions=''),
                     xml().replace('123.5 MiB','NaN MiB'),xml().replace('Fixture GPU','')):
            with self.subTest(text=text):
                self.assertEqual(self.query(text)['exit_code'],1)

    def test_optional_fields_unavailable(self):
        report=self.query(xml(versions='<driver_version>123.45</driver_version>').replace('123.5 MiB','N/A'))
        self.assertIsNone(report['cuda_reported'])
        self.assertIsNone(report['gpus'][0]['free_memory'])
        self.assertEqual(report['exit_code'],0)

    def test_new_driver_labels(self):
        report=self.query(xml(versions='<kmd_version>123.45</kmd_version><cuda_umd_version>12.0</cuda_umd_version>'))
        self.assertEqual(report['driver_version'],'123.45')
        self.assertEqual(report['cuda_reported'],'12.0')

    def test_no_file_access_or_ml_imports(self):
        import builtins
        original_import=builtins.__import__
        def guarded_import(name,*args,**kwargs):
            if name.split('.')[0] in ('torch','transformers','cupy','pycuda','pynvml'):
                raise AssertionError('Heavy module import')
            return original_import(name,*args,**kwargs)
        with patch.object(builtins,'__import__',side_effect=guarded_import), \
             patch.object(builtins,'open',side_effect=AssertionError('File access')), \
             patch.object(check.shutil,'which',return_value='tool'), \
             patch.object(check.subprocess,'run',return_value=SimpleNamespace(stdout=xml(),stderr='',returncode=0)), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(check.main([]),0)

    def test_report_keeps_inference_unverified(self):
        with patch.object(check.shutil,'which',return_value='tool'), \
             patch.object(check.subprocess,'run',return_value=SimpleNamespace(stdout=xml(),stderr='',returncode=0)), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(check.main([]),0)
        for label in ('CUDA runtime compatibility','PyTorch CUDA availability','Actual GPU inference'):
            self.assertIn(label+': UNVERIFIED',output.getvalue())
        self.assertIn('Python:',output.getvalue())


if __name__ == '__main__':
    unittest.main()
