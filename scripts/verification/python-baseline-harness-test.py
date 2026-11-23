"""Behavior checks for the external Python-release measurement harness."""
import importlib.util
import io
from pathlib import Path
import queue
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location(
    "package_measurement", Path(__file__).with_name("measure-python-sdk-baseline.py"))
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)


class BridgeFinalResponseTests(unittest.TestCase):
    def bridge(self, messages):
        bridge = measurement.Bridge.__new__(measurement.Bridge)
        bridge.sequence, bridge.events = 0, []
        bridge.process = SimpleNamespace(stdin=io.StringIO())
        bridge.inbox = queue.Queue()
        for index, message in enumerate(messages):
            bridge.inbox.put((index, message))
        return bridge

    def test_prompt_events_are_observed_before_the_final_response(self):
        started = {"id": "1", "type": "prompt.event", "event": {"type": "run.started"}}
        tool = {"id": "1", "type": "prompt.event", "event": {"type": "tool_result"}}
        final = {"id": "1", "type": "prompt.result", "result": {"success": True}}
        bridge = self.bridge([started, tool, final])
        self.assertEqual(bridge.request("runPrompt")["response"], final)
        self.assertEqual([event for _, event in bridge.events], [started, tool, final])

    def test_other_request_events_do_not_finish_an_index_measurement(self):
        event = {"id": "1", "type": "event", "event": {"type": "progress"}}
        unrelated = {"id": "other", "type": "workspace.indexed"}
        final = {"id": "1", "type": "workspace.indexed", "result": {"files_parsed": 1451}}
        bridge = self.bridge([event, unrelated, final])
        self.assertEqual(bridge.request("indexWorkspace")["response"], final)


if __name__ == "__main__":
    unittest.main()
