import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from yutong_teams.config import Config
from yutong_teams.control import Coordinator
from yutong_teams.core.contracts import HUMAN
from yutong_teams.runtime.progress import apply, projected, MAX_BLOCKS, MAX_CHARS
from yutong_teams.runtime.providers.matlab import MatlabAdapter
import test_runtime as runtime_tests
from test_runtime import MemoryAdapter


class ProgressTest(unittest.TestCase):
    def test_stream_coalescing_tool_updates_and_failure(self):
        r = {"id": "r", "events": []}
        apply(r, "text", {"text": "准备"})
        apply(r, "text", {"text": "检查"})
        apply(r, "tool", {"id": "one", "name": "read", "arguments": {"path": "a"}})
        apply(r, "tool", {"id": "two", "name": "read", "arguments": {"path": "b"}})
        apply(r, "tool_result", {"id": "one", "result": "file a"})
        apply(r, "tool_result", {"id": "two", "result": "missing", "is_error": True})
        self.assertEqual("准备检查", r["trace"][0]["text"])
        self.assertEqual(["completed", "failed"], [b["status"] for b in r["trace"][1:]])
        self.assertEqual("file a", r["trace"][1]["result"])
        self.assertEqual("missing", r["trace"][2]["result"])

    def test_replace_streams_and_hidden_reasoning(self):
        r = {"id": "r"}
        apply(r, "text.replace", {"stream": "first", "text": "initial"})
        apply(r, "tool", {"id": "t", "name": "tool"})
        apply(r, "text.replace", {"stream": "first", "text": "corrected"})
        apply(r, "text.replace", {"stream": "second", "text": "second"})
        apply(r, "agent_thought_chunk", {"text": "not public"})
        self.assertEqual(["corrected", "second"], [b["text"] for b in r["trace"] if b["kind"] == "text"])
        self.assertNotIn("not public", json.dumps(r))

    def test_trace_bounded_and_compaction_does_not_mutate_full_record(self):
        r = {"id": "r"}
        for i in range(140):
            apply(r, "tool", {"id": str(i), "name": "call", "arguments": "x" * 5000})
            apply(r, "text", {"text": "result" * 1000})
        self.assertTrue(r["trace_truncated"])
        self.assertLessEqual(len(r["trace"]), MAX_BLOCKS)
        self.assertLessEqual(len(json.dumps(r["trace"], ensure_ascii=False)), MAX_CHARS)
        saved = copy.deepcopy(r)
        compact = projected(r, compact=True)
        self.assertLessEqual(len(compact["trace"]), 6)
        self.assertEqual(saved, r)

    def test_matlab_public_stream_and_remote_approval_is_not_execution(self):
        events = []
        emit = lambda kind, value: events.append((kind, value))
        MatlabAdapter._progress(dict(phase="progress", data=dict(stream="正在检查", generation=3, phase="generating")), emit)
        MatlabAdapter._progress(dict(phase="tool", data=dict(id="t", name="calc", arguments={"code": "2+2"})), emit)
        MatlabAdapter._progress(dict(phase="toolResult", data=dict(request=dict(id="t", remote=True), reply=dict(approved=True, result="Approved"))), emit)
        self.assertFalse(any(kind == "tool_result" for kind, value in events))
        MatlabAdapter._progress(dict(phase="toolResult", data=dict(request=dict(id="t", name="calc"), reply=dict(approved=True, result="4"))), emit)
        self.assertEqual("text.replace", events[0][0])
        self.assertEqual("matlab-3", events[0][1]["stream"])
        self.assertEqual("4", events[-1][1]["result"])


class TimelineTest(unittest.TestCase):
    def test_commit_order_survives_equal_times_and_clock_rollback(self):
        with tempfile.TemporaryDirectory() as home:
            c = Coordinator(Config(home), start=False)
            try:
                g = c.groups.create(dict(name="order", members=["claude"]))["id"]
                messages = []
                for stamp in ("2026-11-06T11:00:10Z", "2026-11-06T11:00:10Z", "2026-11-06T10:59:00Z"):
                    with patch("yutong_teams.core.messaging.now", return_value=stamp):
                        messages.append(c.messages.send(HUMAN, g, dict(text="message", targets=["claude"])))
                snapshot = c.snapshot()["groups"][0]["messages"]
                self.assertEqual([m["id"] for m in messages], [m["id"] for m in snapshot])
                self.assertEqual(sorted(m["order"] for m in snapshot), [m["order"] for m in snapshot])
                with c.repo.transaction():
                    c.repo.put("message", messages[0])
                self.assertEqual([m["id"] for m in messages], [m["id"] for m in c.snapshot()["groups"][0]["messages"]])
                self.assertEqual("2026-11-06T10:59:00Z", snapshot[-1]["time"])
            finally:
                c.close()


class LiveProjectionTest(unittest.TestCase):
    setUp = runtime_tests.RuntimeTest.setUp
    tearDown = runtime_tests.RuntimeTest.tearDown
    send = runtime_tests.RuntimeTest.send
    wait = runtime_tests.RuntimeTest.wait
    done = runtime_tests.RuntimeTest.done

    def test_progress_is_public_before_completion_and_redacted(self):
        import threading
        started = threading.Event()
        release = threading.Event()
        def behavior(adapter, prompt, turn, stop, emit, approve):
            emit("text", {"text": "检查步骤一"})
            emit("tool", {"id": "large", "name": "reader"})
            emit("tool_result", {"id": "large", "result": "CONFIDENTIAL_FIXTURE" + "x" * 20000})
            started.set()
            release.wait(3)
            return "final"
        MemoryAdapter.behavior = behavior
        with patch.object(self.config, "redact", side_effect=lambda value: str(value).replace("CONFIDENTIAL_FIXTURE", "[redacted]")):
            m = self.send()
            try:
                self.wait(started.is_set)
                run = self.c.snapshot()["runs"][0]
                self.assertEqual("running", run["status"])
                self.assertNotIn("events", run)
                self.assertIn("检查步骤一", json.dumps(run, ensure_ascii=False))
                self.assertNotIn("CONFIDENTIAL_FIXTURE", json.dumps(run))
                detail = self.c.admin_call("run.get", {"id": run["id"]})
                self.assertTrue(detail["events"])
                tool = next(b for b in detail["trace"] if b["kind"] == "tool")
                self.assertEqual("large", tool["call_id"])
                self.assertEqual("completed", tool["status"])
                self.assertTrue(detail["trace_truncated"])
            finally:
                release.set()
            self.wait(lambda: self.done(m["id"]))


if __name__ == "__main__":
    unittest.main()
