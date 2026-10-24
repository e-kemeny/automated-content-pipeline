"""PowerShell installer orchestration tests; all installation commands mocked."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SHELL = shutil.which('pwsh') or shutil.which('powershell')


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(SHELL, 'Windows PowerShell/pwsh required for installer tests')
class InstallerTests(unittest.TestCase):
    def run_setup(self, extra='', flags='-SkipSmokeTest', existing=False, profile=''):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'project space'
            root.mkdir()
            (root/'requirements-export.txt').write_text(profile)
            if existing: (root/'.venv').mkdir()
            def snapshot():
                return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns)
                        if p.is_file() else None for p in root.rglob('*')}
            before = snapshot()
            command = f". {quote(ROOT/'setup.ps1')}; $script:TestRoot={quote(root)}; " + r"""
$script:Created = $false
function Test-SetupPlatform { return $true }
function Find-SetupPython { return @{executable='mock-python'; prefix='global'; base_prefix='global'} }
function Get-SetupPython {
 return @{executable=(Join-Path $script:TestRoot '.venv\Scripts\python.exe');
          prefix=(Join-Path $script:TestRoot '.venv'); base_prefix='global'}
}
function Test-SetupExecutable { param($Name); return $true }
function Confirm-SetupChange { return $true }
function New-SetupEnvironment { param($Python,$Path); Write-Host 'MOCK CREATE'; $script:Created=$true }
function Read-Host { return 'YES' }
function Invoke-SetupTool { param($File,$Arguments); Write-Host ('MOCK RUN '+($Arguments -join ' ')); return @{Code=0;Text='mock diagnostics passed'} }
""" + extra + f"; exit (Invoke-Setup -Root $script:TestRoot {flags})"
            result = subprocess.run([SHELL,'-NoProfile','-NonInteractive','-Command',command],
                                    cwd=temporary,capture_output=True,text=True,timeout=30)
            self.assertEqual(before,snapshot(), result.stdout+result.stderr)
            return result

    def test_all_present_existing_no_reinstall(self):
        for _ in range(2):
            result = self.run_setup(existing=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('MOCK CREATE',result.stdout)
            self.assertIn('environment_check.py',result.stdout)

    def test_multiple_python_candidates_skip_store_alias(self):
        command = f". {quote(ROOT/'setup.ps1')}; " + r"""
function Get-Command { return @(@{Source='C:\Users\test\WindowsApps\python.exe'}, @{Source='C:\PythonOld\python.exe'}, @{Source='C:\Python314\python.exe'}) }
function Get-SetupPython { param($File); if ($File -like '*WindowsApps*') { throw 'Store alias executed' }; if ($File -like '*Python314*') { return @{executable=$File} }; return $null }
$found=Find-SetupPython
if ($found.executable -ne 'C:\Python314\python.exe') { exit 1 }
exit 0
"""
        result=subprocess.run([SHELL,'-NoProfile','-NonInteractive','-Command',command],
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_missing_python(self):
        result=self.run_setup('function Find-SetupPython { return $null }')
        self.assertEqual(result.returncode,1)
        self.assertIn('64-bit Python 3.14',result.stdout)
        self.assertNotIn('MOCK CREATE',result.stdout)

    def test_missing_ffmpeg(self):
        result=self.run_setup("function Test-SetupExecutable { param($Name); return ($Name -ne 'ffmpeg') }")
        self.assertEqual(result.returncode,1)
        self.assertIn('ffmpeg',result.stdout)
        self.assertNotIn('MOCK CREATE',result.stdout)

    def test_missing_ffprobe(self):
        result=self.run_setup("function Test-SetupExecutable { param($Name); return ($Name -ne 'ffprobe') }")
        self.assertEqual(result.returncode,1)
        self.assertIn('ffprobe',result.stdout)

    def test_no_required_packages_and_unreviewed_package_rejected(self):
        result=self.run_setup(profile='not-installed-package==1\n')
        self.assertEqual(result.returncode,1)
        self.assertIn('profile changed',result.stdout)
        self.assertNotIn('MOCK CREATE',result.stdout)

    def test_decline(self):
        result=self.run_setup('function Confirm-SetupChange { return $false }')
        self.assertEqual(result.returncode,1)
        self.assertNotIn('MOCK CREATE',result.stdout)

    def test_approved_creation_and_smoke(self):
        result=self.run_setup(flags='')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stdout.count('MOCK CREATE'),1)
        self.assertIn('portability_smoke.py',result.stdout)
        self.assertIn('-B -S',result.stdout)

    def test_failed_install_preserved(self):
        result=self.run_setup("function New-SetupEnvironment { throw 'interrupted fixture installation' }")
        self.assertEqual(result.returncode,1)
        self.assertIn('interrupted fixture installation',result.stdout)
        self.assertNotIn('MOCK RUN',result.stdout)

    def test_invalid_existing_environment(self):
        result=self.run_setup('function Get-SetupPython { return $null }',existing=True)
        self.assertEqual(result.returncode,1)
        self.assertIn('Preserved',result.stdout)
        self.assertNotIn('MOCK CREATE',result.stdout)

    def test_checkonly_no_writes_outside_repo(self):
        for existing in (False,True):
            result=self.run_setup(flags='-CheckOnly',existing=existing)
            self.assertEqual(result.returncode,0 if existing else 1,result.stdout+result.stderr)
            self.assertNotIn('MOCK CREATE',result.stdout)
            self.assertNotIn('portability_smoke.py',result.stdout)
            self.assertIn('environment_check.py',result.stdout)

    def test_failed_diagnostics_and_smoke(self):
        for name in ('environment_check.py','portability_smoke.py'):
            extra="function Invoke-SetupTool { param($File,$Arguments); if (($Arguments -join ' ') -like '*"+name+"*') { return @{Code=1;Text='fixture error'} }; return @{Code=0;Text='ok'} }"
            result=self.run_setup(extra,flags='',existing=True)
            self.assertEqual(result.returncode,1)
            self.assertIn('FAIL:',result.stdout)

    def test_platform_rejected(self):
        result=self.run_setup('function Test-SetupPlatform { return $false }')
        self.assertEqual(result.returncode,1)
        self.assertIn('Windows and PowerShell',result.stdout)


if __name__ == '__main__':
    unittest.main()
