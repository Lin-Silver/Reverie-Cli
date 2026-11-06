import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from reverie.agent.tool_executor import ToolExecutor
from reverie.session.operation_history import OperationHistory


def test_operation_diagnostics_keep_delivery_without_duplicate_desktop_content():
    history = OperationHistory('session')
    operation = history.add_tool_call('computer_set_value', {'ref': '@s:e1', 'value': 'private text'},
        json.dumps({'ok': True, 'data': {'value': 'private text', 'disposition': {'delivery': 'delivered_unverified', 'retry': 'unsafe'}}}), True, None)
    text = json.dumps(operation.to_dict())
    assert 'private text' not in text
    assert 'delivered_unverified' in text
    assert 'unsafe' in text
    assert '@s:e1' in text


@pytest.mark.parametrize('output', ['["private"]', 'null', '"private"'])
def test_non_object_desktop_output_cannot_break_or_leak_memory_diagnostics(output):
    executor = ToolExecutor.__new__(ToolExecutor)
    memory = Mock()
    executor._get_memory_os = lambda: memory
    executor._tools = {'list_apps': SimpleNamespace(tool_category='desktop')}
    executor.context = {}
    executor._record_memory_event('tool_result', {'tool_name': 'list_apps', 'output': output})
    memory.record_event.assert_called_once()
    assert 'private' not in json.dumps(memory.record_event.call_args.args[1])
