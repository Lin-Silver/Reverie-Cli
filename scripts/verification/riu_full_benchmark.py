"""Frozen full RIU acceptance; retains every completed outcome and actual model output."""
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.runtime/riu-completion-20261021'
RICH_TASKS = ['rich-overview', 'rich-recommendations', 'rich-long-table', 'rich-mixed']
TASKS = RICH_TASKS + ['calculator', 'table', 'chart', 'form', 'comparison', 'text']
PASS = {'first_pass', 'repaired_success'}


def settings_digest():
    sys.path.insert(0, str(ROOT/'ReverieCli-py'))
    from reverie.config import ConfigManager
    cfg = ConfigManager(ROOT).load()
    settings = {name:getattr(cfg,name) for name in ['security','api_proxy','api_max_retries','api_initial_backoff']}
    return hashlib.sha256(json.dumps(settings,sort_keys=True,default=str).encode()).hexdigest()


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix+'.next')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def complete_report(path):
    try:
        report = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(report.get('credential_cleanup'), dict) or not report['credential_cleanup'].get('complete'):
        return None
    cases = report.get('cases', [])
    return report if len(cases) == 1 and cases[0].get('outcome') else None


def request_tool_scope_matches(request):
    sys.path.insert(0, str(ROOT/'ReverieCli-py'))
    from reverie.agent.agent import _static_rich_answer_history
    payload = json.loads(Path(request['request']).read_text(encoding='utf-8'))
    expected = 0 if _static_rich_answer_history(payload.get('messages', [])) else 27
    return request.get('tools') == expected and len(payload.get('tools', [])) == expected


def summarize(entry, report):
    case = report['cases'][0]
    requests = case.get('requests', [])
    actual = sorted({r['response_model'] for r in requests if r.get('response_model')})
    checks = case.get('checks', [])
    complete_flow = (any(c['name'] == 'plain-text-answer' and c['passed'] for c in checks)
                     if entry['task'] == 'text' else bool(case.get('modified_answer') if entry['task'] in RICH_TASKS else case.get('modified_revision'))
                     and any(c['name'] == 'actual-process-restart-recovery' and c['passed'] for c in checks))
    entry.update(state='complete', finished_at_utc=now(), outcome=case['outcome'],
                 repair_count=case.get('repair_count'), generation_first_pass=case.get('generation_first_pass'),
                 actual_models=actual, production_tools_preserved=bool(requests) and all(request_tool_scope_matches(r) for r in requests),
                 checks=len(checks), report_sha256=digest(Path(entry['path'])/'report.json'),
                 http_statuses=dict(Counter(str(r.get('status', 'incomplete')) for r in requests)))
    entry['qualified'] = (entry['outcome'] in PASS and actual == [entry['model']]
                          and entry['production_tools_preserved'] and complete_flow
                          and bool(checks) and all(c['passed'] for c in checks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exe', type=Path, help='Native packaged Desktop executable on the current host.')
    parser.add_argument('--models', nargs='+')
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--api-url', default='https://oai.endpoints.kepler.ai.cloud.ovh.net/v1')
    parser.add_argument('--regression', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--acceptance', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--diagnosis', type=Path, help='Explicit infrastructure diagnosis for an incomplete execution only.')
    parser.add_argument('--formal', action='store_true')
    parser.add_argument('--rich-development', action='store_true', help='Four rich tasks only; explicitly excluded from formal acceptance.')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != ROOT/'.runtime':
        parser.error('Frozen benchmark copies must live directly under repository .runtime so their ROOT remains exact.')
    if args.resume:
        manifest = json.loads((output/'manifest.json').read_text())
        state = json.loads((output/'round.json').read_text())
        if digest(__file__) != manifest['driver_sha256']:
            raise RuntimeError('Driver changed; retain the old round and create a new one.')
        if args.models and args.models != manifest['models']:
            raise RuntimeError('Models changed; create a new round.')
    else:
        if not args.models or (args.formal and (len(args.models) != 2 or args.attempts != 3)):
            parser.error('Formal acceptance requires two actual model IDs and three attempts.')
        regression = json.loads(args.regression.read_text())
        acceptance = json.loads(args.acceptance.read_text())
        assert regression['source_unchanged'] and regression['stages']
        assert all(s['exit_code'] == 0 for s in regression['stages']) and acceptance['passed']
        assert not (args.formal and args.rich_development), 'Development samples cannot be formal.'
        output.mkdir(parents=True, exist_ok=False)
        for name in ['riu_quality_benchmark.py', 'riu_rich_answer_benchmark.py', 'desktop_process.py']:
            shutil.copy2(ROOT/'scripts/verification'/name, output/name)
        (output/'fixtures').mkdir()
        for fixture in ['riu-natural-tasks.json', 'riu-rich-answer-tasks.json']:
            shutil.copy2(ROOT/'scripts/verification/fixtures'/fixture, output/'fixtures'/fixture)
        exe = args.exe.resolve() if args.exe else ROOT/'ReverieCli-ui/release/linux-unpacked/ReverieUI'
        payload = exe.parent.parent if sys.platform == 'darwin' else exe.parent
        core = payload/('reverie.exe' if os.name == 'nt' else 'reverie')
        app_archive = payload/('Resources' if sys.platform == 'darwin' else 'resources')/'app.asar'
        manifest = dict(created_at_utc=now(), formal=args.formal, models=args.models, attempts=args.attempts,
                        scope='Automatic model acceptance only; visual/manual reviews and platform installation acceptance remain separate.',
                        tasks=RICH_TASKS if args.rich_development else TASKS, rich_development=args.rich_development,
                        api_url=args.api_url, max_feedback_repairs=2, turn_timeout_seconds=1800,
                        native_output_cap_added=False, independent_profiles=True, exe=str(exe),
                        build=acceptance['build'], regression=str(args.regression),
                        verification_settings_sha256=settings_digest(),
                        driver_sha256=digest(__file__), sources=json.loads(args.source_manifest.read_text()),
                        frozen_sha256={name:digest(output/name) for name in ['riu_quality_benchmark.py','riu_rich_answer_benchmark.py','desktop_process.py','fixtures/riu-natural-tasks.json','fixtures/riu-rich-answer-tasks.json']},
                        binaries={str(p):digest(p) for p in [exe,core,app_archive]})
        manifest['fixed_manual_review_ids'] = [f'model-{index+1}-{task}-1'
            for task in TASKS if task != 'text' for index in range(len(args.models))] if args.formal else []
        manifest['evidence_sha256'] = {str(p.resolve()): digest(p)
            for p in [args.regression, args.source_manifest, args.acceptance]}
        shutil.copy2(__file__, output/'executed-driver.py')
        write(output/'manifest.json', manifest)
        state = dict(started_at_utc=now(), samples=[], full_acceptance=False,
                     definition='first_pass = no normal feedback; native self-repair/retries and all incidents remain recorded')
        write(output/'round.json', state)

    def guard():
        assert settings_digest() == manifest['verification_settings_sha256'], 'Verification settings changed.'
        for relative, expected in manifest['sources'].items():
            assert digest(ROOT/relative) == expected, 'Source changed: '+relative
        for relative, expected in manifest['frozen_sha256'].items():
            assert digest(output/relative) == expected, 'Frozen verifier changed: '+relative
        for path, expected in manifest['binaries'].items():
            assert digest(path) == expected, 'Native artifact changed: '+path
        for path, expected in manifest['evidence_sha256'].items():
            assert digest(path) == expected, 'Prerequisite evidence changed: '+path

    guard()
    for attempt in range(1, manifest['attempts']+1):
        for task in manifest['tasks']:
            for index, model in enumerate(manifest['models']):
                identifier = f'model-{index+1}-{task}-{attempt}'
                entry = next((e for e in state['samples'] if e['id'] == identifier), None)
                if entry and entry['state'] == 'complete':
                    assert digest(Path(entry['path'])/'report.json') == entry['report_sha256']
                    continue  # Failed verdicts are completed too; never retry them selectively.
                if entry:
                    recovered = complete_report(Path(entry['path'])/'report.json')
                    if recovered:
                        summarize(entry, recovered)
                        entry['collected_after_driver_restart'] = True
                        write(output/'round.json', state)
                        continue
                    if not args.diagnosis:
                        raise RuntimeError('Incomplete execution requires a recorded infrastructure diagnosis: '+identifier)
                    diagnosis = json.loads(args.diagnosis.read_text())
                    assert diagnosis['classification'] == 'infrastructure_interruption' and identifier in diagnosis['cases']
                    partial_file = Path(entry['path'])/'report.json'
                    partial = json.loads(partial_file.read_text()) if partial_file.exists() else {}
                    partial_cases = partial.get('cases', [])
                    if partial_cases:
                        # Never reset an already-started model conversation or its
                        # feedback budget under the name of infrastructure recovery.
                        raise RuntimeError('Model case already started; retain its partial evidence and diagnose/resume that execution without creating a replacement: '+identifier)
                    pid = entry.get('pid')
                    if pid and Path(f'/proc/{pid}/cmdline').exists():
                        command = Path(f'/proc/{pid}/cmdline').read_bytes().decode(errors='replace')
                        if entry['path'] in command:
                            raise RuntimeError('Previous owned child is still running; wait rather than duplicate it.')
                    entry.setdefault('interrupted_executions', []).append(dict(path=entry['path'], diagnosis=str(args.diagnosis), diagnosis_sha256=digest(args.diagnosis)))
                else:
                    entry = dict(id=identifier, model=model, task=task, attempt=attempt, state='running')
                    state['samples'].append(entry)
                execution = len(entry.get('interrupted_executions', []))+1
                case_path = output/(identifier+f'-execution-{execution}')
                assert not case_path.exists()
                guard()
                command = [sys.executable, str(output/('riu_rich_answer_benchmark.py' if task in RICH_TASKS else 'riu_quality_benchmark.py')), '--exe', manifest['exe'],
                           '--output', str(case_path), '--source', 'standard', '--model', model,
                           '--api-url', manifest['api_url'], '--tasks', task, '--attempts', '1',
                           '--max-model-repairs', '2', '--timeout', '1800']
                entry.update(path=str(case_path), started_at_utc=now(), command=command)
                with (output/(identifier+f'-execution-{execution}.txt')).open('x') as log:
                    child = subprocess.Popen(command, cwd=ROOT, env={**os.environ,'DISPLAY':':94'}, stdout=log, stderr=subprocess.STDOUT)
                    entry['pid'] = child.pid
                    write(output/'round.json', state)
                    entry['exit_code'] = child.wait()
                result = complete_report(case_path/'report.json')
                if result is None:
                    write(output/'round.json', state)
                    raise RuntimeError('Child did not produce a completed verdict: '+identifier)
                summarize(entry, result)
                write(output/'round.json', state)
                print(json.dumps({k:entry[k] for k in ['id','model','outcome','qualified','repair_count']}, ensure_ascii=False), flush=True)
    guard()
    generated = [e for e in state['samples'] if e['task'] != 'text']
    text = [e for e in state['samples'] if e['task'] == 'text']
    state.update(finished_at_utc=now(), completed_generation=len(generated), qualified_generation=sum(e['qualified'] for e in generated),
                 completed_text=len(text), qualified_text=sum(e['qualified'] for e in text))
    state['cohort_passed'] = all(e['qualified'] for e in state['samples']) and len(state['samples']) == len(manifest['models'])*manifest['attempts']*len(manifest['tasks'])
    state['automatic_model_acceptance'] = manifest['formal'] and state['cohort_passed']
    state['manual_reviews_status'] = 'pending' if manifest['formal'] else 'not-formal'
    state['full_acceptance'] = False  # Requires the separate fixed visual/manual audit.
    write(output/'round.json', state)
    print(json.dumps({k:v for k,v in state.items() if k != 'samples'}), flush=True)
    return 0 if state['cohort_passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
