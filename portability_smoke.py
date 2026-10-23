"""Real export-only relocation smoke test; synthetic media in a disposable workspace."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
# Explicit export dependency closure: never copy media, artifacts, environments or research.
MODULES = ("pipeline.py", "export_shorts.py", "export_longform.py", "shared_analysis.py",
           "source_identity.py", "transcription.py", "media_probe.py", "windows.py",
           "semantic_events.py", "evaluation.py")

# Run the real CLI, with site packages disabled. Guards observe rather than replace
# exporter validation. Read-only runs may spawn FFprobe only and cannot write files.
GUARD = r"""
import os, runpy, shlex, sys
from pathlib import Path
readonly = '--cache-only' in sys.argv[1:]
def audit(event, args):
    if event == 'import' and args[0].split('.')[0] in (
        'torch', 'transformers', 'faster_whisper', 'ctranslate2', 'open_clip'):
        raise RuntimeError('Heavyweight model import forbidden')
    if event == 'subprocess.Popen':
        allowed = ('ffprobe',) if readonly else ('ffmpeg', 'ffprobe')
        command = args[1]
        executable = args[0] or (shlex.split(command, posix=False)[0].strip(chr(34))
                                 if isinstance(command, str) else command[0])
        if Path(executable).stem.lower() not in allowed:
            raise RuntimeError('Unexpected subprocess')
    if readonly:
        if event == 'open':
            mode, flags = args[1], args[2]
            if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
                raise RuntimeError('Cache-only file write forbidden')
        if event in ('os.mkdir', 'os.remove', 'os.rmdir', 'os.rename', 'os.link',
                     'os.symlink', 'os.truncate', 'os.chmod', 'os.utime'):
            raise RuntimeError('Cache-only filesystem mutation forbidden')
sys.addaudithook(audit)
sys.path.insert(0, os.getcwd())
sys.argv = ['pipeline.py', *sys.argv[1:]]
runpy.run_path('pipeline.py', run_name='__main__')
"""


def pipeline_command(video, analysis, output, cache_only=False):
    command = [sys.executable, '-B', '-S', '-c', GUARD, str(video), '--analysis',
               str(analysis), '--mode', 'both', '--manifest-version', '2',
               '--output-root', str(output)]
    if cache_only:
        command.append('--cache-only')
    return command


def inventory(root):
    """Include directories and file hash/mtime, so unexpected additions also fail."""
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Unexpected fixture symlink')
        if path.is_dir():
            result[str(path.relative_to(root))] = None
        else:
            before = path.stat()
            with path.open('rb') as handle:
                digest = hashlib.file_digest(handle, 'sha256').hexdigest()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('Fixture changed while hashing')
            result[str(path.relative_to(root))] = (digest, after.st_mtime_ns)
    return result


def invoke(workspace, video, analysis, output, *, cache_only=False, rejection=None):
    before = inventory(workspace) if cache_only else None
    result = subprocess.run(pipeline_command(video, analysis, output, cache_only),
                            cwd=workspace, capture_output=True, text=True, timeout=180)
    if cache_only and before != inventory(workspace):
        raise ValueError('Cache-only changed fixture hashes, mtimes or directory inventory')
    text = result.stdout + result.stderr
    if rejection is None:
        if result.returncode or not all(f'{name}: success' in text for name in ('Shorts', 'Long-form')):
            raise ValueError('Both exporters must succeed:\n' + text)
    elif (result.returncode == 0 or rejection not in text or
          not all(f'{name}: failed' in text for name in ('Shorts', 'Long-form'))):
        raise ValueError('Expected both exporters to reject source:\n' + text)
    return text


def create_fixture(workspace):
    from shared_analysis import create_analysis, save_analysis, signal
    from transcription import probe_media
    from windows import build_candidate_windows

    workspace.mkdir()
    for name in MODULES:
        shutil.copy2(ROOT/name, workspace/name)
    video = workspace/'synthetic.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n',
        '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
        '-t', '80', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
        str(video)], check=True, capture_output=True, text=True, timeout=120)
    source = probe_media(video)
    analysis = create_analysis(source)
    # Deliberately synthetic preselected anchors, not detector predictions.
    analysis['candidate_windows'] = signal(
        build_candidate_windows([dict(second=t) for t in (10, 25, 40, 55, 70)],
                                source['duration_seconds']),
        dict(detector='Audio-only', variant='fixed', k=5,
             representation='selected_windows', fixture='synthetic portability only'))
    save_analysis(analysis, workspace/'analysis.json')


def smoke(temp_parent):
    for tool in ('ffmpeg', 'ffprobe'):
        if shutil.which(tool) is None:
            raise ValueError(f'Missing {tool}; add it to PATH')
    # Only this newly created subtree is ever cleaned; no user-provided target is deleted.
    with tempfile.TemporaryDirectory(prefix='portability smoke ', dir=temp_parent) as temporary:
        root = Path(temporary).resolve()
        original = root/'original workspace'
        create_fixture(original)
        invoke(original, 'synthetic.mp4', 'analysis.json', 'portable exports')
        files = list((original/'portable exports').rglob('*.mp4'))
        manifests = list((original/'portable exports').rglob('*manifest.json'))
        if len(files) != 6 or len(manifests) != 2:
            raise ValueError('Expected six MP4s and two manifests')
        invoke(original, 'synthetic.mp4', 'analysis.json', 'portable exports', cache_only=True)
        print('PASS: real V2 creation and original cache-only (both exporters)', flush=True)
        relocated = root/'relocated workspace'
        original.rename(relocated)
        (relocated/'new media').mkdir()
        video = Path('new media')/'synthetic.mp4'
        (relocated/'synthetic.mp4').rename(relocated/video)
        (relocated/'portable exports').rename(relocated/'moved exports')
        invoke(relocated, video, 'analysis.json', 'moved exports', cache_only=True)
        print('PASS: relocated CLI, source and outputs; hashes/mtime_ns unchanged', flush=True)
        path = relocated/video
        original_bytes = path.read_bytes()
        # Append harmless trailing data: still probeable, but content identity differs.
        path.write_bytes(original_bytes + b'changed synthetic content')
        invoke(relocated, video, 'analysis.json', 'moved exports', cache_only=True,
               rejection='Source identity mismatch')
        path.write_bytes(original_bytes)
        path.rename(path.with_suffix('.absent'))
        invoke(relocated, video, 'analysis.json', 'moved exports', cache_only=True,
               rejection='Media file not found')
        print('PASS: modified/missing sources rejected without repair or writes', flush=True)
    print('PASS: temporary fixtures cleaned; no production assets used', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--temp-parent', type=Path, default=ROOT,
                        help='Existing parent for a unique disposable subtree (default: repository)')
    args = parser.parse_args(argv)
    try:
        if not args.temp_parent.is_dir():
            raise ValueError('Temporary parent must be an existing directory')
        smoke(args.temp_parent)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f'FAIL: portability smoke: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
