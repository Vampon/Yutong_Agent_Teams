"""Reusable member personas reference a runtime connection, never its session."""
import uuid


class Profiles:
    def __init__(self, config, registry):
        self.config, self.registry = config, registry

    def validate_source(self, aid):
        source = self.config.agent(aid)
        root_id = source.get("source_id") or source["id"]
        root = self.config.agent(root_id)
        capability = self.registry.get(root["kind"]).capabilities.get("profiles")
        if not capability:
            raise ValueError("此接入方式尚未声明支持独立分身，请在原系统中创建成员后单独接入")
        if capability == "opt_in" and root.get("allow_personas") is not True:
            raise ValueError("请先在 ADP 接入设置中确认应用支持 SystemRole 角色覆盖")
        return root_id

    def create(self, values):
        source = self.config.agent(values["source_id"])
        root_id = self.validate_source(source["id"])
        value = dict(values, source_id=root_id,
                     id=values.get("id") or root_id[:22] + "_" + uuid.uuid4().hex[:8])
        return self.config.save_agent(value, create=True)

    def affected(self, aid):
        return {a["id"] for a in self.config.public()["agents"]
                if a["id"] == aid or a.get("source_id") == aid}
