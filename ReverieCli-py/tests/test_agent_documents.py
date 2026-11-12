from pathlib import Path

import pytest

from reverie.agent.agent import ReverieAgent
from reverie.config import Config


@pytest.fixture
def document_agent(tmp_path, monkeypatch):
    project = tmp_path / 'project'
    project.mkdir()
    home = tmp_path / 'home'
    (home / '.reverie').mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    agent = ReverieAgent('https://example.test', 'test-key', 'test', project_root=project, config=Config())
    agent.get_visible_tool_schemas = lambda: []
    return agent, project, home


def test_both_scopes_and_names_keep_complete_markdown(document_agent):
    agent, project, home = document_agent
    for directory, label in ((home / '.reverie', 'global'), (project, 'project')):
        for filename in ('AGENTS.md', 'Agent.md'):
            (directory / filename).write_text(f'# {label} {filename}\n\n- Preserve this rule.\n```python\nx = 1\n```\n', encoding='utf-8')
    codex = home / '.codex'
    codex.mkdir()
    (codex / 'AGENTS.md').write_text('Not part of Reverie globals', encoding='utf-8')
    messages = agent._build_messages(read_only=True)
    documents = [message['content'] for message in messages if message['content'].startswith('[REVERIE AGENT DOCUMENT]')]
    assert len(documents) == 4
    assert all('# ' in content and '```python\nx = 1\n```' in content for content in documents)
    assert 'global' in documents[0] and 'project' in documents[-1]
    assert 'Not part of Reverie globals' not in str(messages)


def test_edit_remove_and_new_file_refresh_in_active_agent(document_agent):
    agent, project, _ = document_agent
    document = project / 'Agent.md'
    document.write_text('first', encoding='utf-8')
    first = agent.describe_context_usage()
    document.write_text('second version of rules', encoding='utf-8')
    second = agent.describe_context_usage()
    assert first['system_hash'] != second['system_hash']
    assert any('second version of rules' in message['content'] for message in agent._build_messages(read_only=True))
    document.unlink()
    assert not any(message['content'].startswith('[REVERIE AGENT DOCUMENT]') for message in agent._build_messages(read_only=True))


def test_agent_documents_are_separate_from_system_and_history_counts(document_agent):
    agent, project, _ = document_agent
    (project / 'AGENTS.md').write_text('# Rules\nDo not remove headings.\n' * 30, encoding='utf-8')
    agent.messages = [{'role': 'user', 'content': 'Hello'}]
    usage = agent.describe_context_usage()
    segments = {segment['key']: segment for segment in usage['segments']}
    assert segments['agent_documents']['tokens'] > 0
    assert segments['agent_documents']['messages'] == 1
    assert usage['total_tokens'] == sum(item['tokens'] for item in usage['segments']) + usage['overhead_tokens']


def test_measured_context_retains_local_category_disclosure_and_invalidates_on_rule_edit(document_agent):
    agent, project, _ = document_agent
    document = project / 'Agent.md'
    document.write_text('rules', encoding='utf-8')
    agent.messages = [{'role': 'user', 'content': 'Hello'}]
    report = agent.describe_context_usage()
    baseline = {'tokens': 500, 'api_tokens': 500, 'estimated_tokens': report['estimated_history_tokens'],
                'history_hashes': report['history_hashes'], 'system_hash': report['system_hash']}
    agent._apply_api_context_baseline(report, baseline)
    assert report['total_tokens'] == 500 and report['usage_source'] == 'api'
    assert any(segment['key'] == 'agent_documents' for segment in report['estimated_segments'])
    document.write_text('new rules', encoding='utf-8')
    changed = agent.describe_context_usage()
    local_total = changed['total_tokens']
    agent._apply_api_context_baseline(changed, baseline)
    assert changed['total_tokens'] == local_total and changed.get('usage_source') != 'api'
