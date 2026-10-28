"""Install, upgrade and remove real debs in an explicitly disposable container."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def payload_permissions(root):
    """Confirm ordinary desktop users can traverse and read the installed app."""
    root = Path(root)
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode & 0o005 != 0o005:
        return False
    for path in root.rglob('*'):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        if stat.S_ISDIR(mode) and mode & 0o005 != 0o005:
            return False
        if stat.S_ISREG(mode) and (mode & 0o004 == 0 or mode & 0o100 and mode & 0o001 == 0):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--baseline-manifest', type=Path, required=True)
    parser.add_argument('--current-manifest', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--site-packages', type=Path, required=True)
    parser.add_argument('--appimage', type=Path, help='Optional final AppImage to extract-and-run against the same authored fixtures.')
    parser.add_argument('--disposable-container', action='store_true')
    args = parser.parse_args()
    if not (args.disposable_container and Path('/.dockerenv').exists() and os.getuid() == 0):
        raise RuntimeError('Requires explicit disposable-container flag, Docker marker and root')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'.runtime'):
        raise ValueError('Evidence must remain repository-local')
    appimage = args.appimage.resolve() if args.appimage else None
    if appimage and not appimage.is_relative_to(ROOT/'.runtime'):
        raise ValueError('AppImage must remain repository-local')
    status = subprocess.run(['dpkg-query', '-W', '-f=${Status}', 'reverie'], capture_output=True, text=True)
    if status.returncode == 0 and status.stdout.strip() not in {
        'unknown ok not-installed', 'purge ok not-installed', 'deinstall ok config-files',
    }:
        raise RuntimeError('Refusing to change an existing Reverie installation')
    if Path('/opt/Reverie/ReverieUI').exists():
        raise RuntimeError('Refusing to replace an existing desktop payload')
    output.mkdir(parents=True, exist_ok=False)
    user = pwd.getpwuid(1000)
    os.chown(output, user.pw_uid, user.pw_gid)
    report = {'scope': __doc__, 'upgrade_kind': 'same-version distinct native-build upgrade',
              'model_quality_samples': 0, 'stages': [], 'checks': [], 'passed': False,
              'debs': {name: {'path': str(path.resolve()), 'sha256': digest(path)}
                       for name, path in [('baseline', args.baseline), ('current', args.current)]},
              'appimage': {'path': str(appimage), 'sha256': digest(appimage)} if appimage else None}
    installed = False
    display = None

    def run(name, command, *, timeout=360):
        start = time.monotonic()
        with (output/(name+'.txt')).open('x', encoding='utf-8') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT, timeout=timeout)
        report['stages'].append({'name': name, 'exit_code': result.returncode, 'seconds': time.monotonic()-start})
        return result.returncode == 0

    def check(name, passed, detail=None):
        report['checks'].append({'name': name, 'passed': bool(passed), 'detail': detail})

    def native(name, build, compare=None):
        command = ['runuser', '-u', user.pw_name, '--', 'env', 'DISPLAY=:95',
                   'PYTHONPATH='+str(args.site_packages.resolve()), 'python3',
                   str(ROOT/'scripts/verification/riu_restore_native.py'), '--exe', '/opt/Reverie/ReverieUI',
                   '--fixture', str(args.fixture.resolve()), '--profile', str(output/'upgrade-profile'),
                   '--output', str(output/name), '--expected-build', build]
        if compare:
            command += ['--compare', str(compare)]
        else:
            command += ['--seed-state']
        return run(name, command)

    try:
        for label, path in [('baseline', args.baseline), ('current', args.current)]:
            result = subprocess.run(['dpkg-deb', '-f', str(path), 'Package', 'Version', 'Architecture'],
                                    capture_output=True, text=True, check=True)
            check(label+'-package-identity', all(x in result.stdout for x in
                  ['Package: reverie', 'Version: 2.5.0', 'Architecture: amd64']), result.stdout)
        baseline = json.loads(args.baseline_manifest.read_text())
        current = json.loads(args.current_manifest.read_text())
        baseline_id = baseline['build']
        current_id = current['ui']['build']['id']
        check('distinct-native-builds', baseline_id != current_id)
        with (output/'xvfb.txt').open('x') as log:
            display = subprocess.Popen(['Xvfb', ':95', '-screen', '0', '1440x1800x24', '-nolisten', 'tcp', '-ac'],
                                       stdout=log, stderr=log)
        installed = True  # A partial unpack also belongs to this validation run.
        if not run('install-baseline', ['dpkg', '--install', str(args.baseline.resolve())]):
            raise RuntimeError('Baseline dpkg install failed')
        check('baseline-payload-readable-by-desktop-user', payload_permissions('/opt/Reverie'))
        sandbox = Path('/opt/Reverie/chrome-sandbox')
        normalized = (
            run('baseline-sandbox-owner', ['chown', 'root:root', str(sandbox)])
            and run('baseline-sandbox-mode', ['chmod', '4755', str(sandbox)])
            and sandbox.exists()
            and sandbox.stat().st_uid == 0
            and sandbox.stat().st_mode & 0o7777 == 0o4755
        )
        check('baseline-sandbox-ready-for-native-comparison', normalized)
        for relative in ['ReverieUI', 'reverie', 'resources/app.asar']:
            check('baseline-installed-hash-'+relative,
                  digest(Path('/opt/Reverie')/relative) == baseline['all_current_package_file_hashes'][relative])
        check('baseline-restores-real-native-view', native('baseline-native', baseline_id))
        if not run('upgrade-current-unpack', ['dpkg', '--unpack', str(args.current.resolve())]):
            raise RuntimeError('Current dpkg unpack failed')
        if not run('current-sandbox-permission-reset', ['chmod', '0755', str(sandbox)]):
            raise RuntimeError('Could not prepare the sandbox permission hook check')
        if not run('upgrade-current-configure', ['dpkg', '--configure', 'reverie']):
            raise RuntimeError('Current dpkg configure failed')
        check('current-payload-readable-by-desktop-user', payload_permissions('/opt/Reverie'))
        check('current-sandbox-owner-and-setuid', sandbox.exists() and sandbox.stat().st_uid == 0 and
              sandbox.stat().st_mode & 0o7777 == 0o4755)
        for item in current['artifacts']:
            original = Path(item['path'])
            if original.name in ['ReverieUI', 'reverie', 'app.asar']:
                relative = Path('resources/app.asar') if original.name == 'app.asar' else Path(original.name)
                check('current-installed-hash-'+str(relative), digest(Path('/opt/Reverie')/relative) == item['sha256'])
        compare = output/'baseline-native/report.json'
        check('upgraded-native-state-preservation', native('current-native', current_id, compare))
        command = ['runuser', '-u', user.pw_name, '--', 'env', 'DISPLAY=:95',
                   'PYTHONPATH='+str(args.site_packages.resolve()), 'python3',
                   str(ROOT/'scripts/verification/riu_rich_answer_native.py'), '--exe', '/opt/Reverie/ReverieUI',
                   '--output', str(output/'current-rich')]
        check('installed-rich-markdown-renderer', run('current-rich', command))
        if appimage:
            app_tmp = Path('/opt/reverie-appimage-tmp')
            run('appimage-temp-directory', ['mkdir', '-p', str(app_tmp)])
            run('appimage-temp-owner', ['chown', f'{user.pw_uid}:{user.pw_gid}', str(app_tmp)])
            run('appimage-temp-mode', ['chmod', '0700', str(app_tmp)])
            command = ['runuser', '-u', user.pw_name, '--', 'env', 'DISPLAY=:95',
                       'APPIMAGE_EXTRACT_AND_RUN=1', 'TMPDIR='+str(app_tmp),
                       'NO_PROXY=127.0.0.1,localhost', 'PYTHONPATH='+str(args.site_packages.resolve()),
                       'python3', str(ROOT/'scripts/verification/riu_rich_answer_native.py'),
                       '--exe', str(appimage), '--output', str(output/'current-appimage-rich')]
            check('final-appimage-rich-renderer', run('current-appimage-rich', command))
            appimage_report_path = output/'current-appimage-rich/report.json'
            appimage_report = json.loads(appimage_report_path.read_text()) if appimage_report_path.exists() else {}
            check('final-appimage-build-id', appimage_report.get('build', {}).get('id') == current_id,
                  appimage_report.get('build'))
            extracted = sorted(app_tmp.iterdir())
            for item in extracted:
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            check('appimage-extraction-scratch-cleaned', not any(app_tmp.iterdir()),
                  {'removed_test_directories': [item.name for item in extracted]})
    except Exception as error:
        report['error'] = type(error).__name__+': '+str(error)
    finally:
        profile = output/'upgrade-profile'
        retained = {str(p): digest(p) for p in profile.rglob('*') if p.is_file()} if profile.exists() else {}
        if installed or Path('/opt/Reverie/ReverieUI').exists():
            check('dpkg-uninstall', run('uninstall', ['dpkg', '--remove', 'reverie']))
            check('program-and-launchers-removed', all(not p.exists() and not p.is_symlink() for p in
                  [Path('/opt/Reverie/ReverieUI'), Path('/usr/bin/reverie'), Path('/usr/bin/reverieui'),
                   Path('/usr/share/applications/Reverie.desktop')]))
            check('uninstall-preserves-user-profile', bool(retained) and all(Path(p).exists() and digest(Path(p)) == h for p, h in retained.items()))
        if display:
            display.terminate()
            display.wait(timeout=30)
        report['passed'] = not report.get('error') and bool(report['checks']) and all(c['passed'] for c in report['checks'])
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'passed': report['passed'], 'error': report.get('error'),
                      'failed_checks': [c['name'] for c in report['checks'] if not c['passed']]}))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
