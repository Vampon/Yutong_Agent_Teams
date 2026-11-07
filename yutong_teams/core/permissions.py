"""Human-configured policy for approval requests surfaced by native runners.

This is not a filesystem sandbox: native allow/deny rules still apply. Business
questions and delivery reviews deliberately do not pass through this policy.
"""
import copy
from ..config import atomic_json

MODES = ("ask", "auto", "deny")


def effective(config, aid):
    with config.lock:
        agent = config.raw_agent(aid)
        mode = agent.get("permission_mode", "inherit")
        if mode in MODES:
            return mode
        if "permission_mode" not in agent and agent.get("auto_tools"):
            return "auto"  # Compatibility with the earlier hidden setting.
        if agent.get("source_id"):
            return effective(config, agent["source_id"])
        return config.data.get("permissions", {}).get("mode", "ask")


class Permissions:
    def __init__(self, config, repo, registry):
        self.config, self.repo, self.registry = config, repo, registry

    def mode(self, aid):
        return effective(self.config, aid)

    def configure(self, values):
        with self.config.lock:
            data = copy.deepcopy(self.config.data)
            settings = data.setdefault("permissions", {"mode": "ask", "review": True})
            if "mode" in values:
                if values["mode"] not in MODES:
                    raise ValueError("未知工具确认策略")
                settings["mode"] = values["mode"]
            if "review" in values:
                if not isinstance(values["review"], bool):
                    raise ValueError("交付审核必须为布尔值")
                settings["review"] = values["review"]
            overrides = values.get("overrides", {})
            if not isinstance(overrides, dict):
                raise ValueError("成员权限设置应为对象")
            for aid, mode in overrides.items():
                agent = self.config.agent(aid)
                if not self.registry.get(agent["kind"]).capabilities.get("approvals"):
                    raise ValueError("该运行器的工具权限由原平台管理")
                if mode not in MODES + ("inherit",):
                    raise ValueError("未知成员确认策略")
                next(a for a in data["agents"] if a["id"] == aid)["permission_mode"] = mode
            atomic_json(self.config.path, data)
            self.config.data = data
        with self.repo.transaction():
            self.repo.emit("", "permissions.configured", "human", dict(settings, overrides=overrides))
        return self.config.public()["permissions"]
