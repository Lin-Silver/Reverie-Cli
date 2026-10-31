"""Verify an actual packaged desktop on its native OS; synthetic fixtures only."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def package_executable(package: Path) -> Path:
    if sys.platform == 'darwin':
        with (package/'Contents/Info.plist').open('rb') as stream:
            name = plistlib.load(stream)['CFBundleExecutable']
        if Path(name).name != name:
            raise ValueError('Invalid bundle executable name')
        return package/'Contents/MacOS'/name
    return package/('ReverieUI.exe' if os.name == 'nt' else 'ReverieUI')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--sdk-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'.runtime'):
        raise ValueError('Evidence must remain in repository .runtime')
    exe = package_executable(args.package.resolve())
    if not exe.is_file():
        raise FileNotFoundError(exe)
    output.mkdir(parents=True, exist_ok=False)
    with exe.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'scope': __doc__, 'platform': sys.platform, 'executable': str(exe),
              'executable_sha256': digest, 'model_quality_samples': 0, 'stages': [], 'passed': False}
    env = {**os.environ, 'NO_PROXY': '127.0.0.1,localhost'}
    try:
        for name, script in [('p2', 'riu_p2_electron.py'), ('p3', 'riu_p3_electron.py'),
                             ('rich', 'riu_rich_answer_native.py'), ('p4', 'riu_p4_electron.py')]:
            command = [sys.executable, str(ROOT/'scripts/verification'/script), '--exe', str(exe),
                       '--output', str(output/name)]
            if name == 'p3':
                command += ['--sdk-root', str(args.sdk_root.resolve())]
            start = time.monotonic()
            with (output/(name+'.txt')).open('x', encoding='utf-8') as log:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            report['stages'].append({'name': name, 'exit_code': result.returncode,
                                     'seconds': time.monotonic()-start})
            result.check_returncode()
        home = output/'isolation-home'
        home.mkdir()
        command = [str(exe), '--riu-isolation-probe', '--riu-probe-report', str(output/'isolation.json')]
        with (output/'isolation.txt').open('x', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT,
                env={**env, 'PORTABLE_EXECUTABLE_DIR': str(home), 'REVERIE_APP_ROOT': str(home/'core')},
                stdout=log, stderr=subprocess.STDOUT, timeout=180)
        report['stages'].append({'name': 'isolation', 'exit_code': result.returncode})
        result.check_returncode()
        isolation = json.loads((output/'isolation.json').read_text(encoding='utf-8'))
        if not isolation['checks'] or not all(c['passed'] for c in isolation['checks']):
            raise AssertionError('Isolation checks failed')
        report['passed'] = True
    except Exception as error:
        report['error'] = type(error).__name__+': '+str(error)
    finally:
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
