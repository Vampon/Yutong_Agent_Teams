import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

from yutong_teams.config import Config
from yutong_teams.control import Coordinator
from yutong_teams.core.contracts import HUMAN, Principal, Conflict, Forbidden
from yutong_teams.runtime.providers.http import HttpAdapter
import test_runtime as runtime_tests
from test_runtime import MemoryAdapter


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = Config(self.tmp.name)
        self.c = Coordinator(self.config, start=False)
        self.c.bind("http://127.0.0.1:1")

    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()

    def clone(self, source="claude", **values):
        return self.c.admin_call("agent.clone", dict(source_id=source, name="评审分身", role="需求评审", **values))

    def test_connection_and_credentials_are_inherited_not_copied(self):
        source = self.config.agent("claude")
        source.update(command="old-runtime", secret_env="TEAMS_TEST_SECRET")
        self.config.save_agent(source)
        with patch.dict(os.environ, {"TEAMS_TEST_SECRET": "fixture-secret"}):
            clone = self.clone(instructions="独立工作说明")
            raw = self.config.raw_agent(clone["id"])
            self.assertNotIn("command", raw)
            self.assertNotIn("secret_env", raw)
            self.assertNotIn(clone["id"], self.config.secrets)
            self.assertEqual("fixture-secret", self.config.secret(clone))
            self.assertTrue(next(a for a in self.config.public()["agents"] if a["id"] == clone["id"])["has_secret"])
            source.update(command="new-runtime", args=["--model", "test"])
            self.c.admin_call("agent.save", source)
            resolved = Config(self.tmp.name).agent(clone["id"])
            self.assertEqual("new-runtime", resolved["command"])
            self.assertEqual("独立工作说明", resolved["instructions"])
            self.assertEqual("需求评审", resolved["role"])

    def test_duplicate_and_cyclic_or_changed_source_cannot_replace_members(self):
        a = self.clone(id="reviewer")
        with self.assertRaises(ValueError):
            self.clone(id="reviewer")
        with self.assertRaises(ValueError):
            self.config.save_agent(dict(a, source_id=a["id"]))
        with self.assertRaises(ValueError):
            self.c.admin_call("agent.save", dict(a, source_id="deepseek"))
        second = self.clone(source=a["id"])
        self.assertEqual("claude", second["source_id"])
        self.assertEqual("claude", self.config.agent("reviewer")["source_id"])

    def test_capability_gate_and_adp_explicit_opt_in(self):
        self.config.save_agent(dict(id="external", name="外部系统", kind="external"))
        for source in ("external", "adp"):
            with self.assertRaises(ValueError):
                self.clone(source)
        root = self.config.agent("adp")
        root["allow_personas"] = True
        self.c.admin_call("agent.save", root)
        clone = self.clone("adp", instructions="企业规范评审")
        self.assertEqual("adp", clone["kind"])
        with self.assertRaises(ValueError):
            self.c.admin_call("agent.save", dict(root, allow_personas=False))

    def test_permission_inheritance_persistence_and_atomic_validation(self):
        a = self.clone()
        self.c.admin_call("permissions.configure", {"mode": "auto"})
        self.assertEqual("auto", self.c.permissions.mode(a["id"]))
        self.c.admin_call("permissions.configure", {"overrides": {"claude": "deny"}})
        self.assertEqual("deny", self.c.permissions.mode(a["id"]))
        self.c.admin_call("permissions.configure", {"overrides": {a["id"]: "ask"}})
        self.assertEqual("ask", self.c.permissions.mode(a["id"]))
        before = self.config.public()
        with self.assertRaises(ValueError):
            self.c.admin_call("permissions.configure", {"mode": "deny", "overrides": {"adp": "auto"}})
        self.assertEqual(before, Config(self.tmp.name).public())

    def test_policy_does_not_resolve_questions_or_reviews(self):
        g = self.c.groups.create(dict(name="existing", members=["claude"]))
        p = Principal(actor_id="claude", group_id=g["id"])
        q = self.c.attention.create(p, g["id"], "question", "选择验收基线")
        task = self.c.tasks.create(HUMAN, g["id"], dict(title="交付", agent_id="claude"))
        self.c.tasks.update(p, g["id"], task["id"], dict(action="submit", version=task["version"], text="实际结果"))
        self.c.admin_call("permissions.configure", dict(mode="auto", review=False))
        for request in self.c.repo.list("request"):
            self.assertEqual("pending", request["status"])
        with self.assertRaises(Forbidden):
            self.c.attention.resolve_policy(q["id"], "auto")
        self.assertTrue(self.c.repo.require("group", g["id"])["review"])
        self.assertFalse(self.c.groups.create(dict(name="new", members=["claude"]))["review"])

    def test_member_cannot_configure_permissions_or_create_profiles(self):
        g = self.c.groups.create(dict(members=["claude"]))
        p = Principal(actor_id="claude", group_id=g["id"])
        for op, data in (("permissions.configure", {"mode": "auto"}),
                         ("agent.clone", {"source_id": "claude", "name": "fake"})):
            with self.assertRaises(ValueError):
                self.c.agent_call(p, op, data)


class ProfileRuntimeTest(unittest.TestCase):
    setUp = runtime_tests.RuntimeTest.setUp
    tearDown = runtime_tests.RuntimeTest.tearDown
    send = runtime_tests.RuntimeTest.send
    wait = runtime_tests.RuntimeTest.wait
    done = runtime_tests.RuntimeTest.done

    def ready(self):
        self.c.registry.get("fixture").capabilities.update(profiles=True, approvals=True)
        return self.c.admin_call("agent.clone", dict(source_id="one", name="分身", role="评审", instructions="PROFILE_PRIVATE_MARKER"))

    def test_distinct_identity_session_memory_and_prompt(self):
        clone = self.ready()
        self.c.groups.add_member(self.g, clone["id"])
        seen = {}
        def behavior(adapter, prompt, turn, stop, emit, approve):
            seen[adapter.aid] = prompt
            adapter.binding["invoke"]("message.reply", dict(reply_to=turn["message_id"], text=adapter.aid, mode="mail"))
            return "done"
        MemoryAdapter.behavior = behavior
        a, b = self.send(), self.send(clone["id"])
        self.wait(lambda: self.done(a["id"]) and self.done(b["id"]))
        sessions = [self.c.repo.require("session", self.g + ":" + aid) for aid in ("one", clone["id"])]
        self.assertNotEqual(sessions[0]["generation"], sessions[1]["generation"])
        self.assertNotEqual(sessions[0]["provider_id"], sessions[1]["provider_id"])
        self.assertNotIn("PROFILE_PRIVATE_MARKER", seen["one"])
        self.assertIn("PROFILE_PRIVATE_MARKER", seen[clone["id"]])
        self.assertEqual(2, len(MemoryAdapter.instances))
        self.assertNotEqual(*[x.binding["directory"] for x in MemoryAdapter.instances])
        self.assertNotEqual(*[x.binding["connection"]["token"] for x in MemoryAdapter.instances])
        self.assertEqual({"one", clone["id"]}, {m["author"] for m in self.c.repo.list("message") if m["author"] != "human"})

    def test_live_permission_change_resolves_wait_and_keeps_session(self):
        self.ready()
        answers = []
        def behavior(a, p, t, stop, emit, approve):
            answers.append(approve("write_file", {"path": "fixture.txt"}))
            return "done"
        MemoryAdapter.behavior = behavior
        m = self.send()
        self.wait(lambda: bool(self.c.repo.list("request")))
        generation = self.c.repo.require("session", self.g + ":one")["generation"]
        self.c.admin_call("permissions.configure", {"overrides": {"one": "auto"}})
        self.wait(lambda: self.done(m["id"]))
        request = self.c.repo.list("request")[0]
        self.assertEqual([True], answers)
        self.assertEqual({"allow": True, "policy": "auto"}, request["response"])
        run = next(r for r in self.c.repo.list("run") if r["message_id"] == m["id"])
        tool = next(b for b in run["trace"] if b["kind"] == "tool")
        self.assertEqual("auto", tool["permission"])
        self.assertEqual("running", tool["status"])  # Permission does not prove execution.
        self.assertEqual(generation, self.c.repo.require("session", self.g + ":one")["generation"])
        self.c.admin_call("permissions.configure", {"overrides": {"one": "deny"}})
        m = self.send()
        self.wait(lambda: self.done(m["id"]))
        self.assertEqual([True, False], answers)
        self.assertEqual(1, len(self.c.repo.list("request")))
        self.assertEqual(1, len(MemoryAdapter.instances))
        decisions = [e for e in self.c.repo.events(self.g) if e["kind"] == "tool.permission"]
        self.assertEqual([True, False], [e["data"]["allow"] for e in decisions])

    def test_source_edit_is_blocked_while_a_clone_runs(self):
        clone = self.ready()
        self.c.groups.add_member(self.g, clone["id"])
        def behavior(a, p, t, stop, emit, approve):
            return str(approve("fixture-write", {}))
        MemoryAdapter.behavior = behavior
        m = self.send(clone["id"])
        self.wait(lambda: bool(self.c.repo.list("request")))
        with self.assertRaises(Conflict):
            self.c.admin_call("agent.save", self.config.agent("one"))
        self.c.admin_call("attention.answer", dict(id=self.c.repo.list("request")[0]["id"], allow=False))
        self.wait(lambda: self.done(m["id"]))


class ADPProfileTest(unittest.TestCase):
    def test_role_override_and_conversation_isolation_on_wire(self):
        with tempfile.TemporaryDirectory() as root:
            config = Config(root)
            response = MagicMock()
            response.iter_lines.return_value = ["data: " + json.dumps({"Type": "response.completed", "Response": {
                "Status": "success", "Messages": [{"Type": "reply", "Contents": [{"Type": "text", "Text": "ok"}]}]}}), ""]
            a = dict(id="adp", kind="adp", url="https://fixture.invalid/chat", user_id="fixture")
            with patch("yutong_teams.runtime.providers.http.httpx.Client") as client:
                client.return_value.stream.return_value.__enter__.return_value = response
                for agent, generation in ((a, "one"), (dict(a, id="review", source_id="adp", allow_personas=True, role="评审", instructions="审查边界"), "one"),
                                          (dict(a, id="developer", source_id="adp", allow_personas=True, role="开发"), "one"), (a, "two")):
                    driver = HttpAdapter(config, agent, {"generation": generation}, {}, lambda **kw: None)
                    self.assertEqual("ok", driver.run("test", dict(id="r", group_id="g"), threading.Event(), lambda *x: None, lambda *x: False))
                bodies = [call.kwargs["json"] for call in client.return_value.stream.call_args_list]
                self.assertNotIn("SystemRole", bodies[0])
                self.assertEqual("评审\n审查边界", bodies[1]["SystemRole"])
                self.assertEqual(4, len({b["ConversationId"] for b in bodies}))


if __name__ == "__main__":
    unittest.main()
