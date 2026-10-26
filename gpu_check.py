"""Read-only NVIDIA metadata; no CUDA initialization, ML imports or installation."""
import argparse
import platform
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


UNVERIFIED = 'UNVERIFIED'


def optional_text(value):
    value = (value or '').strip()
    return None if value in ('', 'N/A', '[N/A]', 'Not Supported') else value


def memory(value):
    """Keep reported MiB values; unavailable is not zero or allocatable capacity."""
    value = optional_text(value)
    if value is not None and not re.fullmatch(r'\d+(?:\.\d+)? MiB', value):
        raise ValueError('Malformed GPU memory value')
    return value


def parse_report(text):
    root = ET.fromstring(text)
    if root.tag != 'nvidia_smi_log':
        raise ValueError('Unexpected NVIDIA XML root')
    count = (root.findtext('attached_gpus') or '').strip()
    if not count.isdigit() or int(count) != len(root.findall('gpu')):
        raise ValueError('Missing or inconsistent GPU count')
    driver = optional_text(root.findtext('kmd_version')) or optional_text(root.findtext('driver_version'))
    if driver is None:
        raise ValueError('Missing driver version')
    gpus = []
    for index, node in enumerate(root.findall('gpu')):
        name = optional_text(node.findtext('product_name'))
        if name is None:
            raise ValueError('Missing GPU name')
        gpus.append(dict(index=index, id=node.get('id'), name=name,
                         free_memory=memory(node.findtext('fb_memory_usage/free')),
                         total_memory=memory(node.findtext('fb_memory_usage/total'))))
    return dict(hardware='DETECTED' if gpus else 'NOT DETECTED', driver='AVAILABLE',
                driver_version=driver,
                cuda_reported=optional_text(root.findtext('cuda_umd_version')) or
                              optional_text(root.findtext('cuda_version')), gpus=gpus,
                error=None, exit_code=0)


def inspect_gpu():
    unknown = dict(hardware=UNVERIFIED, driver=UNVERIFIED, driver_version=None,
                   cuda_reported=None, gpus=[], error=None, exit_code=1)
    executable = shutil.which('nvidia-smi')
    if executable is None:
        return dict(unknown, error='nvidia-smi unavailable on PATH; hardware/driver presence cannot be established')
    try:
        result = subprocess.run([executable, '-q', '-x'], capture_output=True,
                                text=True, check=False, timeout=10)
        # This message indicates no devices visible to the tool, not physical absence.
        if (result.stdout + result.stderr).strip().casefold() == 'no devices were found':
            return dict(unknown, hardware='NOT DETECTED', exit_code=0,
                        error='nvidia-smi reports no devices; driver availability remains UNVERIFIED')
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()[:300]
            return dict(unknown, error=f'nvidia-smi query failed (exit {result.returncode}): {detail}')
        return parse_report(result.stdout)
    except subprocess.TimeoutExpired:
        return dict(unknown, error='nvidia-smi query timed out after 10 seconds')
    except (OSError, UnicodeError, ET.ParseError, ValueError) as exc:
        return dict(unknown, error=f'GPU query unavailable or malformed: {exc}')


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    print(f'OS: {platform.system()} {platform.release()} | machine: {platform.machine()}')
    print(f'Python: {platform.python_version()} | {64 if sys.maxsize > 2**32 else 32}-bit | {sys.executable}')
    report = inspect_gpu()
    print(f'NVIDIA hardware: {report["hardware"]} (visibility through nvidia-smi only)')
    print(f'NVIDIA driver: {report["driver"]}; version: {report["driver_version"] or UNVERIFIED}')
    print(f'Driver-reported CUDA: {report["cuda_reported"] or UNVERIFIED} (not an installed runtime check)')
    for gpu in report['gpus']:
        print(f'GPU {gpu["index"]} [{gpu["id"] or "unknown ID"}]: {gpu["name"]}; '
              f'free: {gpu["free_memory"] or UNVERIFIED}; total: {gpu["total_memory"] or UNVERIFIED}')
    if report['error']:
        print(report['error'])
    print('CUDA runtime compatibility: UNVERIFIED')
    print('PyTorch CUDA availability: UNVERIFIED')
    print('Actual GPU inference: UNVERIFIED')
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
