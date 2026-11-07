import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from yutong_teams.config import Config
from yutong_teams.runtime.providers.deepseek_config import resolve, launch_patch
from yutong_teams.runtime.providers.acp import ACPAdapter


class ModelConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"DSH_HOME": str(self.root)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def write(self, profile, rows):
        p = self.root / "profiles" / profile / "cordis.patch.yml"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rows), "utf-8")
        return p

    def web(self):
        return self.write("web", [
            {"id": "llm-pi-ai", "config": {"providers": {"huoshan": {"apiKeyEnv": "HUOSHAN_API_KEY", "api": "openai-completions", "baseURL": "https://fixture.invalid/v1", "models": [{"id": "review-model"}]}}}},
            {"id": "agent-default-model", "config": {"provider": "huoshan", "model": "review-model"}},
            {"id": "web-server", "config": {"port": 9999}},
        ])

    def test_auto_bridges_only_model_rows_without_reading_credentials(self):
        source = self.web()
        before = source.read_bytes()
        (self.root / ".credentials.yaml").write_text("not valid yaml: [", "utf-8")
        plan = resolve({})
        self.assertEqual(("huoshan", "review-model"), (plan["provider"], plan["model"]))
        args = launch_patch(plan, self.root / "owned-session")
        payload = json.loads(Path(args[1]).read_text("utf-8"))
        self.assertEqual(["llm-pi-ai", "agent-default-model", "acp"], [x["id"] for x in payload])
        self.assertEqual("HUOSHAN_API_KEY", payload[0]["config"]["providers"]["huoshan"]["apiKeyEnv"])
        self.assertEqual(before, source.read_bytes())

    def test_explicit_acp_and_launch_patches_are_not_overwritten(self):
        self.web()
        self.assertEqual([], resolve({"args": ["--patch", "native.yml"]})["patches"])
        self.write("acp", [{"id": "acp", "config": {"provider": "native", "model": "existing", "sessionListPageSize": 20}}])
        plan = resolve({})
        self.assertEqual("native", plan["provider"])
        self.assertEqual(20, plan["patches"][-1]["config"]["sessionListPageSize"])
        self.assertEqual(["acp"], [x["id"] for x in plan["patches"]])

    def test_explicit_file_model_and_missing_default(self):
        source = self.web()
        plan = resolve({"dsh_config_path": str(source), "model_provider": "huoshan", "model": "other"})
        self.assertEqual("other", plan["model"])
        with self.assertRaisesRegex(ValueError, "同时填写"):
            resolve({"model_provider": "huoshan"})
        self.write("web", [{"id": "llm-pi-ai", "config": {"providers": {"gateway": {}}}}])
        with self.assertRaisesRegex(ValueError, "未选择默认模型"):
            resolve({})

    def test_missing_and_malformed_config_fail_without_leaking_content(self):
        self.assertEqual([], resolve({})["patches"])
        with self.assertRaisesRegex(ValueError, "找不到"):
            resolve({"dsh_config_path": str(self.root / "missing.yml")})
        p = self.web()
        p.write_text('sensitive-marker: [', 'utf-8')
        with self.assertRaises(ValueError) as error:
            resolve({})
        self.assertNotIn("sensitive-marker", str(error.exception))


class ModelSelectionTest(unittest.TestCase):
    def driver(self, turns=0):
        self.saved = {}
        driver = ACPAdapter(None, {"kind": "deepseek"}, {"provider_id": "saved", "turns": turns}, {}, lambda **kw: self.saved.update(kw))
        driver.model_plan = {"provider": "huoshan", "model": "chosen", "source": "fixture.yml"}
        driver._request = lambda method, params: (method, params)
        return driver

    def state(self, route):
        value = lambda p, m: json.dumps([p, m])
        return {"configOptions": [{"id": "model", "category": "model", "currentValue": value(*route),
            "options": [{"group": "huoshan", "options": [{"name": "Chosen", "value": value("huoshan", "chosen")}]}]}]}

    def test_failed_first_turn_selects_advertised_route_and_verifies_ack(self):
        d = self.driver()
        with patch.object(d, "_wait", return_value=self.state(("huoshan", "chosen"))) as wait:
            d._select_model(self.state(("deepseek-official", "default")), True, threading.Event(), time.monotonic()+10, lambda *x:None, lambda *x:False)
            method, params = wait.call_args.args[0]
            self.assertEqual("session/set_config_option", method)
            self.assertEqual(["huoshan", "chosen"], json.loads(params["value"]))
            self.assertEqual("huoshan", self.saved["model_provider"])
        with patch.object(d, "_wait", return_value=self.state(("deepseek-official", "default"))):
            with self.assertRaisesRegex(RuntimeError, "未确认模型切换"):
                d._select_model(self.state(("deepseek-official", "default")), True, threading.Event(), time.monotonic()+10, lambda *x:None, lambda *x:False)

    def test_established_session_keeps_model_and_unknown_choice_fails(self):
        d = self.driver(turns=2)
        with patch.object(d, "_wait") as wait:
            d._select_model(self.state(("existing", "saved-model")), True, threading.Event(), time.monotonic()+10, lambda *x:None, lambda *x:False)
            wait.assert_not_called()
            self.assertEqual("existing", self.saved["model_provider"])
        d = self.driver()
        d.model_plan["model"] = "absent"
        with self.assertRaisesRegex(RuntimeError, "未提供所选模型"):
            d._select_model(self.state(("deepseek-official", "default")), False, threading.Event(), time.monotonic()+10, lambda *x:None, lambda *x:False)


if __name__ == "__main__":
    unittest.main()
