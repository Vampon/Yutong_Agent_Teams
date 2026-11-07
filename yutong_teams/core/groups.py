from pathlib import Path
from .access import actor_key
from .contracts import HUMAN, Forbidden, now, uid, require_text


class Groups:
    def __init__(self, repo, access, config):
        self.repo, self.access, self.config = repo, access, config

    def create(self, values):
        members = list(dict.fromkeys(values.get("members", [])))
        if not members:
            raise ValueError("至少选择一位成员")
        for aid in members:
            self.config.agent(aid)
        leader = values.get("leader") or members[0]
        if leader not in members:
            raise ValueError("队长必须属于当前协作")
        workspace = str(Path(values.get("workspace") or self.config.root / "workspace").resolve())
        if not Path(workspace).is_dir():
            raise ValueError("工作目录不存在")
        gid = uid()
        group = dict(id=gid, group_id=gid, name=require_text(values.get("name", "新协作"), "名称", 100),
                     workspace=workspace, leader=leader, paused=False,
                     review=bool(values.get("review", self.config.data.get("permissions", {}).get("review", True))),
                     max_turns=min(100, max(2, int(values.get("max_turns", 24)))), created=now())
        with self.repo.transaction():
            self.repo.put("group", group)
            self.repo.put("context", dict(id=gid, group_id=gid, version=1, brief=str(values.get("goal", ""))[:12000],
                                          decisions=[], handoffs=[], constraints=[]))
            for aid in members:
                self.add_member(gid, aid)
            self.repo.emit(gid, "group.created", "human", {"name": group["name"], "members": members})
        return group

    def add_member(self, gid, aid):
        a = self.config.agent(aid)
        key = actor_key(gid, aid)
        with self.repo.transaction():
            existing = self.repo.get("actor", key)
            if existing:
                existing["enabled"] = True
                self.repo.put("actor", existing)
                return existing
            member = dict(id=key, group_id=gid, actor_id=aid, enabled=True,
                          mode="external" if a["kind"] == "external" else "managed", created=now())
            self.repo.put("actor", member)
            self.repo.put("session", dict(id=key, group_id=gid, actor_id=aid, generation=uid(),
                                          provider_id="", state="offline" if member["mode"] == "external" else "stopped",
                                          fingerprint="", last_seen="", error="", started="", turns=0))
            self.repo.emit(gid, "actor.joined", "human", {"actor_id": aid, "mode": member["mode"]})
            return member

    def update(self, values):
        gid = values["id"]
        with self.repo.transaction():
            group = self.repo.require("group", gid)
            if any(r["status"] in ("running", "waiting", "starting") for r in self.repo.list("run", gid)):
                raise ValueError("请先暂停协作，等待当前执行停止")
            members = list(dict.fromkeys(values.get("members", [])))
            if not members or values.get("leader") not in members:
                raise ValueError("至少保留一位成员，队长必须在成员中")
            if any(t["agent_id"] not in members and t["status"] not in ("done", "cancelled") for t in self.repo.list("task", gid)):
                raise ValueError("有未完成任务的成员不能移除")
            if any(d["recipient"] not in members and d["recipient"] != "human" and not d.get("replied_at")
                   and d["state"] in ("queued", "offered", "uncertain") for d in self.repo.list("delivery", gid)):
                raise ValueError("请先处理该成员尚未交接的消息")
            workspace = str(Path(values.get("workspace", group["workspace"])).resolve())
            if not Path(workspace).is_dir():
                raise ValueError("工作目录不存在")
            for aid in members:
                self.add_member(gid, aid)
            for actor in self.repo.list("actor", gid):
                actor["enabled"] = actor["actor_id"] in members
                self.repo.put("actor", actor)
            group.update(name=require_text(values.get("name", group["name"]), "名称", 100), leader=values["leader"],
                         workspace=workspace, review=bool(values.get("review", True)),
                         max_turns=min(100, max(2, int(values.get("max_turns", 24)))))
            self.repo.put("group", group)
            self.repo.emit(gid, "group.updated", "human", {"members": members})
            return group

    def pause(self, gid, paused):
        with self.repo.transaction():
            group = self.repo.require("group", gid)
            group["paused"] = bool(paused)
            self.repo.put("group", group)
            if not paused:
                for root in self.repo.list("budget", gid):
                    root["used"] = 0
                    self.repo.put("budget", root)
            self.repo.emit(gid, "group.paused" if paused else "group.resumed", "human", {})

    def context(self, p, gid):
        self.access.group(p, gid)
        value = self.repo.require("context", gid)
        value["agents"] = self.repo.list("actor_context", gid)
        return value

    def update_context(self, p, gid, values):
        from .contracts import Conflict
        with self.repo.transaction():
            self.access.group(p, gid)
            ctx = self.repo.require("context", gid)
            if values.get("version") != ctx["version"]:
                raise Conflict("共享上下文已更新，请重新读取后修改")
            if "brief" in values or "constraints" in values:
                self.access.manager(p, gid)
            if "brief" in values:
                ctx["brief"] = str(values["brief"])[:12000]
            if "constraints" in values:
                if not isinstance(values["constraints"], list) or not all(isinstance(x, str) for x in values["constraints"]):
                    raise ValueError("约束应为文本数组")
                ctx["constraints"] = [x[:2000] for x in values["constraints"][:50]]
            for field in ("decision", "handoff"):
                if values.get(field):
                    bucket = "decisions" if field == "decision" else "handoffs"
                    ctx[bucket].append(dict(id=uid(), by=p.actor_id, text=require_text(values[field], field, 10000), time=now()))
            ctx["version"] += 1
            self.repo.put("context", ctx)
            self.repo.emit(gid, "context.updated", p.actor_id, {"version": ctx["version"], "fields": list(values)})
            return ctx
