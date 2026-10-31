"""Exploratory Harness² adapter running the real Reverie prompt CLI.

Uses the upstream recursion, selection and experience library unchanged. The
editor is deterministic; executors use a local protocol fixture, the explicitly
selected anonymous Vireonix service, or Agnes through an external loopback
bridge that alone holds the real credentials. These are integration smokes,
not JobBench/LAB/WorkBuddy scores or formal model-quality acceptance samples.
Only synthetic workspaces and four prompt components are editable. Product
tools, executor, approvals, session locks and sandbox remain on their normal path.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import signal
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ReverieCli-py"))
PIN = "1cfe254e8d25b15f37048c3730134686abe60335"
COMPONENTS = ("systemprompt.md", "guardrails.md", "LongTermMEMORY.md", "tool_descriptions/tool_guidance.md")
GUARDRAILS = "Respect the user's tool scope. Never disable approvals, session locks, workspace boundaries or sandbox.\n"
PROMPT = ("仅使用 file_ops 的 read 操作读取 inventory.txt；先读取，再回答文件中的项目、数量和标识。"
          "请逐行按“项目：原值”“数量：原值”“标识：原值”输出，保留原值，不添加其他内容。"
          "不要修改任何文件，不要执行命令，也不要使用其他工具。")


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def validate_agnes_bridge_url(value):
    """Accept only an explicit local HTTP /v1 bridge without URL secrets."""
    raw = str(value or '')
    if not raw or any(char.isspace() or ord(char) < 32 for char in raw) or '?' in raw or '#' in raw:
        raise ValueError('Agnes requires an explicit HTTP loopback bridge URL ending in /v1')
    parsed = urllib.parse.urlsplit(raw)
    if (parsed.scheme != 'http' or parsed.path not in ('/v1', '/v1/')
            or not re.fullmatch(r'(?:127\.0\.0\.1|localhost)(?::[1-9][0-9]{0,4})?', parsed.netloc, re.I)):
        raise ValueError('Agnes bridge must use http://127.0.0.1[:port]/v1 or http://localhost[:port]/v1')
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError('Agnes bridge port must be between 1 and 65535') from error
    # Use an IP literal after validation so localhost resolution cannot change
    # the bridge destination. No redirect or environment proxy is allowed below.
    return f'http://127.0.0.1{":" + str(port) if port else ""}/v1'


def provider_request_timeout(provider):
    return 90 if provider == 'agnes' else 65


def cli_execution_timeout(provider, timeout=None):
    return timeout if timeout is not None else (210 if provider == 'agnes' else 100)


def configure_executor(cfg, provider, recorder_url, agnes_model='agnes-3.0-flash'):
    """Keep Agnes on its native provider path with an invalid local-only key."""
    from reverie.config import ModelConfig

    if provider == 'agnes':
        cfg.models = []
        cfg.agnes = {**cfg.agnes, 'enabled': True, 'api_key': 'local-recorder-only',
                     'selected_model_id': agnes_model, 'api_url': recorder_url,
                     'live_model_list': False, 'max_tokens': 4096,
                     'timeout': provider_request_timeout(provider)}
        cfg.active_model_source = 'agnes'
    else:
        cfg.models = [ModelConfig('auto' if provider == 'vireonix' else 'h2-fixture',
                                 'Harness2 exploratory executor', recorder_url, '')]
        cfg.active_model_source = 'standard'
    cfg.active_model_index = 0
    cfg.stream_responses, cfg.api_max_retries, cfg.api_timeout, cfg.api_proxy = False, 0, provider_request_timeout(provider), ''
    cfg.api_enable_debug_logging = False
    cfg.auto_index = False


def execution_environment(home, state):
    # Do not read or inherit Agnes secrets; only the external bridge needs
    # real Agnes credentials. The CLI talks to this adapter with a placeholder.
    env = {name: os.environ[name] for name in os.environ if name not in ('AGNES_API_KEY', 'AGNES_TOKEN')}
    env.update(HOME=str(home), REVERIE_APP_ROOT=str(state), NO_PROXY='127.0.0.1,localhost',
               no_proxy='127.0.0.1,localhost', PYTHONPATH=str(ROOT / 'ReverieCli-py'))
    return env


class NoBridgeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


def inventory_tool_scope(calls, workspace):
    """Check every proposed tool operation against the user's exact read scope."""
    allowed = []
    for call in calls:
        try:
            arguments = json.loads(call.get('arguments', '{}'))
            requested = Path(arguments.get('path', ''))
            target = (workspace / requested).resolve()
            allowed.append(call.get('name') == 'file_ops' and arguments.get('operation') == 'read'
                           and bool(arguments.get('path')) and target == (workspace / 'inventory.txt').resolve())
        except (ValueError, TypeError, AttributeError):
            allowed.append(False)
    return any(allowed), bool(allowed) and all(allowed)


def completed_delivery(run_dir):
    """A partial answer is retained as evidence, never adopted as a delivery."""
    run_dir = Path(run_dir)
    try:
        execution = json.loads((run_dir / 'execution.json').read_text(encoding='utf-8'))
        return (isinstance(execution, dict)
                and type(execution.get('exit_code')) is int and execution['exit_code'] == 0
                and execution.get('execution_success') is True
                and bool((run_dir / 'answer.txt').read_text(encoding='utf-8').strip()))
    except (OSError, ValueError, TypeError):
        return False


def inventory_fields(text):
    """Parse the task's three complete labelled values, rejecting ambiguity."""
    if not isinstance(text, str):
        return None
    fields = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'\s*(项目|数量|标识)\s*[：:]\s*(.*?)\s*', line)
        if not match or not match[2] or match[1] in fields:
            return None
        fields[match[1]] = match[2]
    return fields if set(fields) == {'项目', '数量', '标识'} else None


def has_inventory_read_observation(trajectory):
    """Require correlated tool evidence, not a proposed action or a final answer."""
    reads = set()
    observed = False
    for line in trajectory.splitlines():
        if line.startswith('[ERROR]'):
            return False
        if not line.startswith(('[ACTION] ', '[OBSERVATION] ')):
            continue
        kind, raw = line.split(' ', 1)
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                return False
            call_id = value.get('tool_call_id')
            if kind == '[ACTION]':
                arguments = value.get('arguments', '{}')
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
                if not isinstance(arguments, dict) or not isinstance(call_id, str) or not call_id:
                    return False
                workspace = value.get('workspace')
                if workspace:
                    scoped = {**value, 'arguments': json.dumps(arguments)}
                    valid = inventory_tool_scope([scoped], Path(workspace))[1]
                else:
                    # Missing provenance cannot establish that an absolute or
                    # nested path is the task's requested file.
                    valid = (value.get('name') == 'file_ops' and arguments.get('operation') == 'read'
                             and arguments.get('path') in ('inventory.txt', './inventory.txt'))
                if not valid:
                    return False
                reads.add(call_id)
            elif (call_id in reads and value.get('tool_name') in (None, 'file_ops')
                  and inventory_fields(value.get('content')) is not None):
                observed = True
        except (ValueError, TypeError, AttributeError):
            return False
    return observed


def inventory_values_match(actual, source):
    expected = inventory_fields(source)
    return expected is not None and inventory_fields(actual) == expected


def execution_trajectory(messages, workspace, *, exit_code, execution_success, error=''):
    """Keep tool-call IDs so reflection can distinguish a result from a claim."""
    lines = []
    for message in messages:
        for call in message.get('tool_calls', []) or []:
            action = {**call.get('function', {}), 'tool_call_id': call.get('id'),
                      'workspace': str(Path(workspace).resolve())}
            lines.append('[ACTION] ' + json.dumps(action, ensure_ascii=False))
        if message.get('role') == 'tool':
            lines.append('[OBSERVATION] ' + json.dumps({
                'tool_call_id': message.get('tool_call_id'), 'tool_name': message.get('name'),
                'content': message.get('content', '')}, ensure_ascii=False))
    if exit_code != 0 or execution_success is not True or error:
        lines.append('[ERROR] ' + (str(error) if error else f'Execution did not complete successfully (exit {exit_code}).'))
    return '\n'.join(lines)


@contextmanager
def app_root(path):
    previous = os.environ.get("REVERIE_APP_ROOT")
    os.environ["REVERIE_APP_ROOT"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("REVERIE_APP_ROOT", None)
        else:
            os.environ["REVERIE_APP_ROOT"] = previous


class Transport:
    """Capture exact bodies; bound upstream calls without inventing credentials."""

    def __init__(self, output, provider, budget, *, agnes_base_url=None):
        self.output, self.provider, self.budget = output, provider, budget
        self.agnes_base_url = validate_agnes_bridge_url(agnes_base_url) if provider == 'agnes' else None
        self.bridge_opener = (urllib.request.build_opener(urllib.request.ProxyHandler({}), NoBridgeRedirect())
                              if provider == 'agnes' else None)
        self.records = []
        self.lock = threading.Lock()
        self.forwarded = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                payload = json.loads(raw)
                with owner.lock:
                    index = len(owner.records)
                    record = {"index": index, "stream": payload.get("stream"), "tools": len(payload.get("tools", [])),
                              "started_at": datetime.now(timezone.utc).isoformat(), "request_sha256": hashlib.sha256(raw).hexdigest()}
                    owner.records.append(record)
                    allowed = owner.forwarded < owner.budget
                    if allowed:
                        owner.forwarded += 1
                prefix = owner.output / f"request-{index:03}"
                prefix.with_suffix('.json').write_bytes(raw)
                started = time.monotonic()
                try:
                    if not allowed:
                        status, body = 429, json.dumps({"error": {"message": "Exploratory upstream request budget exhausted"}}).encode()
                        record['budget_blocked'] = True
                    elif owner.provider == 'fixture':
                        messages = payload.get('messages', [])
                        results = [m for m in messages if m.get('role') == 'tool']
                        if results:
                            # Exercise the actual tool result. No fixture answer is injected from disk.
                            content = str(results[-1].get('content', ''))
                            fields = re.findall(r'(?:项目|数量|标识)：[^\n]+', content)
                            message, finish = {"role": "assistant", "content": '\n'.join(fields)}, 'stop'
                        else:
                            message, finish = {"role": "assistant", "content": None, "tool_calls": [{
                                "id": "read-inventory", "type": "function", "function": {
                                    "name": "file_ops", "arguments": '{"operation":"read","path":"inventory.txt"}'}}]}, 'tool_calls'
                        status, body = 200, json.dumps({"id": f"h2-fixture-{index}", "object": "chat.completion",
                            "created": int(time.time()), "model": "h2-fixture", "choices": [{"index": 0,
                            "message": message, "finish_reason": finish}]}).encode()
                    else:
                        url = (f'{owner.agnes_base_url}/chat/completions' if owner.provider == 'agnes'
                               else 'https://vireonix.ai/v1/chat/completions')
                        request = urllib.request.Request(url, data=raw,
                            headers={"Content-Type": "application/json", "Accept": "application/json"})
                        try:
                            if owner.provider == 'agnes':
                                # The bridge owns official-endpoint authentication. Never
                                # forward the CLI's local placeholder Authorization header.
                                response = owner.bridge_opener.open(request, timeout=provider_request_timeout(owner.provider))
                            else:
                                # Keep certificate validation enabled, including the managed proxy CA.
                                context = ssl.create_default_context(cafile=os.environ.get('CODEX_PROXY_CERT') or None)
                                response = urllib.request.urlopen(request, timeout=65, context=context)
                            with response:
                                status, body = response.status, response.read()
                        except urllib.error.HTTPError as error:
                            status, body = error.code, error.read()
                    prefix.with_suffix('.response').write_bytes(body)
                    try:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict):
                            record['response_model'] = parsed.get('model')
                            if parsed.get('usage'):
                                record['usage'] = parsed['usage']
                    except ValueError:
                        pass
                    record.update(status=status, elapsed_seconds=round(time.monotonic() - started, 3),
                                  response_sha256=hashlib.sha256(body).hexdigest())
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as error:
                    record.update(error=type(error).__name__ + ': ' + str(error))
                    try:
                        self.send_error(502, 'Exploratory transport failed; inspect recorded error')
                    except OSError:
                        pass
                finally:
                    with owner.lock:
                        dump(owner.output / 'requests.json', owner.records)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


def run(args):
    from harness2.core import prompts, tree
    from harness2.core.proposer import Proposer, Reply
    from harness2.core.schedule import run_domain
    from harness2.core.spec import BenchPrompts, BenchSpec, ChannelSpec
    from harness2.core.tree import SurfaceSpec
    from reverie.config import ConfigManager
    from reverie.context_engine.workspace import detect_workspace_profile
    from reverie.session.manager import SessionManager

    # The pinned upstream prompt registry only ships OpenCode/Codex metadata.
    # Add a scoped Reverie description; leave recursion/selection/library code
    # and the on-disk upstream checkout untouched. Fail if this private API moves.
    surface_text = ('# Editable Reverie prompt components\nOnly systemprompt.md, LongTermMEMORY.md, '
                    'and tool_descriptions/tool_guidance.md may be changed. guardrails.md is immutable. '
                    'These texts become additional workspace rules; they do not replace the core system prompt. '
                    'No scripts, skills, plugins or subagents are installed by this adapter. '
                    'Never edit workspace inputs or product code.\n')
    previous_surface = prompts._SURFACE_TEXTS.get('reverie')
    prompts._SURFACE_TEXTS['reverie'] = prompts._SurfaceText(
        surface_md=surface_text, inv='Clarify general read-only tool procedure from observed trajectories. {levers}',
        dom='Clarify reporting of observed inventory fields without retaining task-specific values. {levers}',
        tts_surface=surface_text)

    class ReverieSubstrate:
        name = "reverie"

        def surface(self):
            return SurfaceSpec(name='reverie', always_on=COMPONENTS, always_on_max=12000,
                always_on_cap_reason='Bound exploratory prompt overhead', skill_dir='skills', skill_name_rule='must_match',
                trigger_hint='Name the skill in tool guidance.', autotrigger_file='guardrails.md',
                trigger_line='When {desc}, load {name}.', subagent_requires_mode=True, plugin_dir=None, hooks_file=None)

    class Adapter:
        def __init__(self, root):
            self.root, self.substrate = root, ReverieSubstrate()
            channel = ChannelSpec('opencode', 'local/deterministic-editor')
            self.spec = BenchSpec(name='reverie-smoke', runs_root=root / 'runs', install_mode='workspace_config',
                prompts=BenchPrompts(work='read a synthetic inventory and report the observed fields'),
                channels={'proposer': channel, 'selector': channel}, allow_subagents=False)
            self.execution_lock = threading.Lock()
            self.executions = []
            base = {name: '' for name in COMPONENTS}
            base['systemprompt.md'] = 'Read the requested local inventory and report observed fields faithfully.\n'
            base['guardrails.md'] = GUARDRAILS
            tree.write_tree(self.substrate.surface(), base, self.base_harness(), stubs=False)
            for index in range(args.max_tasks):
                source = self.task_files(f'inventory-{index + 1}')
                source.mkdir(parents=True)
                (source / 'inventory.txt').write_text(f'项目：晨星{index + 1}\n数量：{17 + index * 6}\n标识：松林{index + 1}\n', encoding='utf-8')

        def tasks(self, split='all'):
            return [f'inventory-{i + 1}' for i in range(args.max_tasks)]

        def domain_of(self, task_id):
            return 'read-only-inventory'

        def task_prompt(self, task_id):
            return PROMPT

        def task_files(self, task_id):
            return self.root / 'sources' / task_id

        def base_harness(self):
            return self.root / 'base'

        def validate_tree(self, harness):
            if set(harness) - set(COMPONENTS):
                raise ValueError('This exploratory adapter only materialises the four always-on prompt components.')
            if harness.get('guardrails.md') != GUARDRAILS:
                raise ValueError('Product security guardrails are immutable in this exploratory adapter.')

        def execute(self, task_id, harness_dir, run_id, *, timeout=None):
            # Serialise full CLI processes: independent profiles, bounded free service load.
            with self.execution_lock:
                return self._execute(task_id, harness_dir, run_id, timeout=timeout)

        def _execute(self, task_id, harness_dir, run_id, *, timeout):
            run_dir = self.root / 'executions' / run_id
            run_dir.mkdir(parents=True, exist_ok=False)
            workspace, home, state = [run_dir / n for n in ('workspace', 'home', 'app-root')]
            for directory in (workspace, home, state):
                directory.mkdir()
            subprocess.run(['git', '-c', 'init.templateDir=', '-c', 'init.defaultBranch=verification',
                            'init', '--quiet', str(workspace)], check=True, capture_output=True)
            profile = detect_workspace_profile(workspace)
            if profile.instruction_layers or Path(profile.vcs_root).resolve() != workspace:
                raise RuntimeError('Exploratory workspace inherited parent instructions')
            original = (self.task_files(task_id) / 'inventory.txt').read_bytes()
            (workspace / 'inventory.txt').write_bytes(original)
            component_tree = tree.read_tree(self.substrate.surface(), harness_dir or self.base_harness())
            self.validate_tree(component_tree)
            with app_root(state):
                manager = ConfigManager(workspace)
                manager.ensure_dirs()
                cfg = manager.load()
                configure_executor(cfg, args.provider, f'http://127.0.0.1:{transport.server.server_port}/v1', args.agnes_model)
                manager.save(cfg)
                (manager.project_data_dir / 'rules.txt').write_text(tree.always_on_text(self.substrate.surface(), component_tree), encoding='utf-8')
                report_path = run_dir / 'prompt-report.json'
                env = execution_environment(home, state)
                cli = [str(args.cli_exe.resolve())] if args.cli_exe else [sys.executable, '-m', 'reverie']
                command = [*cli, str(workspace), '--no-index',
                           '--prompt', PROMPT, '--report-file', str(report_path)]
                with (run_dir / 'cli.log').open('x') as log:
                    process = subprocess.Popen(command, env=env, cwd=workspace, stdout=log, stderr=log,
                                               start_new_session=True)
                    try:
                        exit_code = process.wait(timeout=cli_execution_timeout(args.provider, timeout))
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=5)
                        exit_code = 124
                prompt_report = json.loads(report_path.read_text()) if report_path.exists() else {}
                session = SessionManager(manager.project_data_dir, project_root=workspace).load_session(prompt_report.get('session_id', ''))
            messages = session.messages if session else []
            dump(run_dir / 'messages.json', messages)
            transcript = execution_trajectory(messages, workspace, exit_code=exit_code,
                execution_success=prompt_report.get('success'), error=prompt_report.get('error', ''))
            (run_dir / 'trajectory.md').write_text(transcript, encoding='utf-8')
            if prompt_report.get('output_text'):
                (run_dir / 'answer.txt').write_text(prompt_report['output_text'], encoding='utf-8')
            meta = {'task': task_id, 'run_id': run_id, 'exit_code': exit_code,
                    'timeout_seconds': cli_execution_timeout(args.provider, timeout),
                    'component_fingerprint': hashlib.sha256(json.dumps(component_tree, sort_keys=True).encode()).hexdigest(),
                    'inventory_unchanged': (workspace / 'inventory.txt').read_bytes() == original,
                    'execution_success': prompt_report.get('success') is True}
            dump(run_dir / 'execution.json', meta)
            self.executions.append(run_dir)
            return run_dir

        def delivered(self, run_dir):
            return completed_delivery(run_dir)

        def trajectory(self, run_dir, *, obs_trunc):
            return (run_dir / 'trajectory.md').read_text()

        def deliverable_text(self, run_dir):
            path = run_dir / 'answer.txt'
            return path.read_text() if path.exists() else ''

        def deliverable_files(self, run_dir):
            return {'answer.txt': self.deliverable_text(run_dir)} if self.delivered(run_dir) else {}

    class ScopeEditor(Proposer):
        """Deterministic prompt edits; no model-generated optimization is claimed."""
        def call(self, mission, context_dir, label, **kwargs):
            context = Path(context_dir)
            workspace = None
            if label.startswith('experience.'):
                observed = any(has_inventory_read_observation(p.read_text()) for p in (context / 'rollouts').glob('*.md'))
                text = ('<experience>\ncue: A user requests a local read-only inventory\n'
                        'lesson: Keep the explicit file_ops read scope and report only observed fields.\n'
                        'evidence: The retained trajectory contains a file_ops action and its returned inventory.\n'
                        'confidence: limited to the observed synthetic tool flow; no causal quality gain claimed\n'
                        '</experience>') if observed else 'NO_ENTRY'
            else:
                workspace = context / 'harness'
                guidance = workspace / 'tool_descriptions/tool_guidance.md'
                guidance.parent.mkdir(exist_ok=True)
                guidance.write_text('For an explicit file_ops read-only request, call file_ops with operation=read and the requested path. '
                                    'Wait for the tool result, then report its observed fields. Do not substitute retrieval or shell tools.\n')
                text = '<notes>Make the explicit read-only tool scope concrete; keep all product guardrails unchanged.</notes>'
            reply = Reply(label=label, text=text, ok=True, attempts=1, workspace=workspace)
            self._calls.append(reply)
            return reply

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    transport = Transport(output, args.provider, args.max_requests, agnes_base_url=args.agnes_base_url)
    adapter = Adapter(output)
    modes = ('agg', 'seq') if args.mode == 'both' else ('agg' if args.mode == 'parallel' else 'seq',)
    try:
        result = run_domain('read-only-inventory', adapter.tasks(), 1, adapter=adapter,
            prop=ScopeEditor(adapter.spec.channels['proposer']), runs_root=adapter.spec.runs_root,
            library_root=output / 'library', modes=modes)
        # Only after selection/reflection: no verdict or expected answer enters editor evidence.
        checks = []
        for run_dir in sorted(adapter.executions):
            meta = json.loads((run_dir / 'execution.json').read_text())
            messages = json.loads((run_dir / 'messages.json').read_text())
            calls = [call.get('function', {}) for message in messages for call in message.get('tool_calls', []) or []]
            source = (adapter.task_files(meta['task']) / 'inventory.txt').read_text()
            answer = adapter.deliverable_text(run_dir)
            valid_read, scope_preserved = inventory_tool_scope(calls, run_dir / 'workspace')
            conditions = {'cli_succeeded': meta['exit_code'] == 0 and meta['execution_success'],
                'read_executed': valid_read, 'tool_result_present': any(m.get('role') == 'tool' for m in messages),
                'tool_returned_inventory': any(m.get('role') == 'tool' and inventory_values_match(str(m.get('content', '')), source) for m in messages),
                'scope_preserved': scope_preserved,
                'answer_matches_observed_fields': inventory_values_match(answer, source),
                'input_unchanged': meta['inventory_unchanged']}
            checks.append({**meta, 'checks': conditions, 'passed': all(conditions.values())})
        report = {'schema': 'reverie.harness2.exploration.v1', 'harness2_revision': PIN,
            'evaluation_contract': 'completed execution, correlated inventory read, exact labelled field values',
            'provider': args.provider, 'editor': 'deterministic scope editor; not model optimization',
            'model_source': 'agnes' if args.provider == 'agnes' else 'standard',
            'model': args.agnes_model if args.provider == 'agnes' else ('auto' if args.provider == 'vireonix' else 'h2-fixture'),
            'bridge': ({'base_url': args.agnes_base_url, 'authentication': 'external in-memory bridge only',
                        'cli_credential': 'invalid local-recorder-only placeholder; no real key inherited',
                        'payload': 'native Agnes provider request forwarded unchanged'} if args.provider == 'agnes' else None),
            'timeouts_seconds': {'request': provider_request_timeout(args.provider),
                                 'default_cli': cli_execution_timeout(args.provider)},
            'cli': str(args.cli_exe.resolve()) if args.cli_exe else 'source: python -m reverie',
            'cli_sha256': hashlib.sha256(args.cli_exe.read_bytes()).hexdigest() if args.cli_exe else None,
            'formal_model_quality_samples': 0, 'official_benchmark_score': None,
            'upstream_workflow': result, 'executions': checks, 'requests': transport.records,
            'library_entries': [str(p.relative_to(output)) for p in (output / 'library').rglob('EXPERIENCE.md')],
            'passed': result['failed'] == 0 and bool(checks) and all(c['passed'] for c in checks)}
        dump(output / 'report.json', report)
        print(json.dumps({'passed': report['passed'], 'executions': len(checks), 'requests': len(transport.records),
                          'failed_executions': [c['run_id'] for c in checks if not c['passed']],
                          'library_entries': len(report['library_entries'])}))
        return 0 if report['passed'] else 1
    finally:
        transport.close()
        if previous_surface is None:
            prompts._SURFACE_TEXTS.pop('reverie', None)
        else:
            prompts._SURFACE_TEXTS['reverie'] = previous_surface


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--harness2-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider', choices=('fixture', 'vireonix', 'agnes'), default='fixture')
    parser.add_argument('--agnes-base-url', help='External credential-holding HTTP loopback bridge /v1 URL; never an official API URL')
    parser.add_argument('--agnes-model', default='agnes-3.0-flash', help='Agnes text model for the isolated exploratory profile')
    parser.add_argument('--mode', choices=('parallel', 'sequential', 'both'), default='sequential')
    parser.add_argument('--max-tasks', type=int, default=2)
    parser.add_argument('--max-requests', type=int, default=40)
    parser.add_argument('--cli-exe', type=Path, help='Optional actual standalone or Desktop embedded Reverie kernel')
    args = parser.parse_args()
    if args.provider == 'agnes':
        try:
            args.agnes_base_url = validate_agnes_bridge_url(args.agnes_base_url)
        except ValueError as error:
            parser.error(str(error))
        if (not re.fullmatch(r'agnes-[A-Za-z0-9][A-Za-z0-9._-]*', args.agnes_model)
                or args.agnes_model.startswith(('agnes-image-', 'agnes-video-'))):
            parser.error('--agnes-model must name an Agnes text model')
    elif args.agnes_base_url:
        parser.error('--agnes-base-url requires --provider agnes')
    source = args.harness2_source.resolve()
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=source, text=True)
    if revision != PIN or dirty:
        parser.error(f'Use an unmodified google-research/harness2 checkout at {PIN}')
    if not args.output.resolve().is_relative_to(ROOT / '.runtime') or not 1 <= args.max_tasks <= 3:
        parser.error('Use a fresh output under .runtime and 1–3 synthetic tasks')
    if args.provider in ('vireonix', 'agnes') and (args.max_tasks != 1 or args.max_requests > 8 or args.mode == 'both'):
        parser.error('The live smoke is limited to one task, one mode, and at most eight upstream requests')
    if not 1 <= args.max_requests <= 100:
        parser.error('Use a request budget between 1 and 100')
    if args.cli_exe and not args.cli_exe.is_file():
        parser.error('--cli-exe must point to an existing Reverie kernel executable')
    sys.path.insert(0, str(source))
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
