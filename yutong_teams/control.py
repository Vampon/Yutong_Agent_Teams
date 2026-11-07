"""Composition root for the shared collaboration control plane.

All frontends and agent tools call these services. Provider processes are owned
by Supervisor; they never mutate SQLite or fabricate identities themselves.
"""
import json
import threading
from pathlib import Path
from .core.access import Access, actor_key
from .core.attention import Attention
from .core.contracts import HUMAN, Principal, Forbidden, Conflict, now
from .core.groups import Groups
from .core.messaging import Messaging
from .core.migration import import_v1
from .core.repository import Repository
from .core.sessions import Sessions
from .core.tasks import Tasks
from .core.profiles import Profiles
from .core.permissions import Permissions


class Coordinator:
    def __init__(self, config, start=True, registry=None):
        from .runtime.registry import default_registry
        from .runtime.supervisor import Supervisor
        self.config = config
        (config.root / "workspace").mkdir(exist_ok=True)
        self.repo = Repository(config.root / "collaboration.db")
        import_v1(self.repo, config.root)
        self.access = Access(self.repo)
        self.groups = Groups(self.repo, self.access, config)
        self.messages = Messaging(self.repo, self.access)
        self.attention = Attention(self.repo, self.access)
        self.tasks = Tasks(self.repo, self.access, self.attention)
        self.sessions = Sessions(self.repo, self.access)
        self.registry = registry or default_registry()
        self.profiles = Profiles(config, self.registry)
        self.permissions = Permissions(config, self.repo, self.registry)
        self.endpoint = ""
        self.connection_lock = threading.RLock()
        from .interfaces.gateway import Gateway
        self.gateway = Gateway(self)
        self.supervisor = Supervisor(self)
        self.supervisor.recover_interrupted()
        if start:
            self.supervisor.start()

    def bind(self, endpoint):
        self.endpoint = endpoint.rstrip("/")
        from .config import atomic_json
        for path in (self.config.root / "connections").glob("*.json"):
            value = json.loads(path.read_text("utf-8"))
            value["endpoint"] = self.endpoint
            atomic_json(path, value)

    def snapshot(self):
        from .runtime.progress import projected
        with self.repo.transaction():
            groups = []
            for group in self.repo.list("group"):
                gid = group["id"]
                group["members"] = [a["actor_id"] for a in self.repo.list("actor", gid) if a["enabled"]]
                group["actors"] = self.repo.list("actor", gid)
                group["context"] = self.repo.require("context", gid)
                group["goal"] = group["context"]["brief"]
                group["tasks"] = self.repo.list("task", gid)
                group["deliveries"] = self.repo.list("delivery", gid)
                messages = self.repo.ordered("message", gid)
                pending = {d["message_id"] for d in group["deliveries"] if d["state"] not in ("dismissed", "cancelled")
                           and (not d["read_at"] or (d["mode"] == "request_reply" and not d["replied_at"]) or d["state"] == "uncertain")}
                recent = {m["id"] for m in messages[-300:]}
                group["messages"] = [m for m in messages if m["id"] in recent or m["id"] in pending]
                group["sessions"] = self.repo.list("session", gid)
                group["actor_context"] = self.repo.list("actor_context", gid)
                group["activity"] = self.repo.recent(gid)
                groups.append(group)
            all_runs = self.repo.ordered("run")
            recent_ids = {r["id"] for r in all_runs[-100:]}
            runs = [projected(r, compact=True) for r in all_runs
                    if r["id"] in recent_ids or r["status"] in ("running", "waiting", "starting")]
            for run in runs:
                run.pop("prompt", None)
                run["result"] = run.get("result", "")[:1000]
                run.pop("events", None)  # Raw events are available through run.get.
            return dict(revision=self.repo.revision(), groups=groups, requests=self.repo.list("request"),
                        runs=runs, config=self.config.public(), catalog=self.registry.catalog(), home=str(self.config.root))

    def agent_call(self, p, op, data):
        """Identity comes from transport authentication, never request arguments."""
        gid = p.group_id
        self.access.group(p, gid)
        if self.repo.require("actor", actor_key(gid, p.actor_id))["mode"] == "external":
            self.sessions.heartbeat(p, gid)
        if op == "context.get":
            ctx = self.groups.context(p, gid)
            ctx["roster"] = [dict(actor_id=a["actor_id"], name=self.config.agent(a["actor_id"])["name"],
                                   role=self.config.agent(a["actor_id"]).get("role", ""))
                             for a in self.repo.list("actor", gid) if a["enabled"]]
            ctx["leader"] = self.repo.require("group", gid)["leader"]
            return ctx
        if op == "context.update":
            return self.groups.update_context(p, gid, data)
        if op == "message.send":
            return self.messages.send(p, gid, data)
        if op == "message.reply":
            if not data.get("reply_to"):
                raise ValueError("回复必须指定 reply_to")
            return self.messages.send(p, gid, data)
        if op == "message.history":
            limit = min(100, max(1, int(data.get("limit", 30))))
            return self.repo.list("message", gid)[-limit:]
        if op == "inbox.list":
            return self.messages.inbox(p, gid, data.get("limit", 50), unread=data.get("unread", True))
        if op == "inbox.read":
            return self.messages.read_inbox(p, gid, data.get("message_ids"))
        if op == "delivery.ack":
            return self.messages.acknowledge(p, gid, data["message_id"], data["stage"])
        if op == "inbox.claim":
            self.sessions.heartbeat(p, gid)
            return self.messages.inbox(p, gid, data.get("limit", 1), claim=True)
        if op == "task.list":
            return self.repo.list("task", gid)
        if op == "task.create":
            return self.tasks.create(p, gid, data)
        if op == "task.update":
            task = self.tasks.update(p, gid, data["id"], data)
            self._notify_completed(task)
            return task
        if op == "human.request":
            options = data.get("options", [])
            if not isinstance(options, list) or not all(isinstance(x, str) for x in options) or len(options) > 8:
                raise ValueError("选项应为至多 8 项文本")
            return self.attention.create(p, gid, "question", data["title"], data.get("detail", ""), options=options)
        if op == "human.status":
            item = self.repo.require("request", data["id"])
            if item["group_id"] != gid or item["actor_id"] != p.actor_id:
                raise Forbidden("只能查看自己的确认事项")
            return item
        if op == "actor.status":
            return self.sessions.status(p, gid, data)
        if op == "session.connect":
            return self.sessions.connect(p, gid, data)
        if op == "session.heartbeat":
            return self.sessions.heartbeat(p, gid)
        if op == "events.list":
            return self.repo.events(gid, data.get("after", 0), data.get("limit", 100))
        raise ValueError("未知成员操作：" + op)

    def admin_call(self, op, data):
        if op == "state":
            return self.snapshot()
        if op == "group.create":
            return self.groups.create(data)
        if op == "group.update":
            return self.groups.update(data)
        if op == "group.pause":
            paused = not data.get("resume", False)
            self.groups.pause(data["group_id"], paused)
            if paused:
                self.supervisor.stop_group(data["group_id"])
            return True
        if op == "message.send":
            return self.messages.send(HUMAN, data["group_id"], data)
        if op == "message.read":
            return self.messages.acknowledge(HUMAN, data["group_id"], data["message_id"], "read")
        if op == "message.recover":
            delivery = self.messages.recover(data["group_id"], data["id"], data["action"])
            if data["action"] == "retry":
                self.supervisor.enable(data["group_id"], delivery["recipient"])
            return delivery
        if op == "task.add":
            return self.tasks.create(HUMAN, data["group_id"], data)
        if op == "task.action":
            task = self.tasks.update(HUMAN, data["group_id"], data["id"], data)
            self._notify_completed(task)
            if data["action"] == "cancel":
                self.supervisor.cancel_task(task["id"])
            elif data["action"] in ("start", "retry", "revise"):
                self.supervisor.enable(task["group_id"], task["agent_id"])
            return task
        if op == "context.update":
            return self.groups.update_context(HUMAN, data["group_id"], data)
        if op == "attention.answer":
            request = self.repo.require("request", data["id"])
            if request["kind"] == "review":
                task = self.repo.require("task", request["task_id"])
                task = self.tasks.update(HUMAN, request["group_id"], task["id"],
                                         dict(version=task["version"], action="approve" if data.get("allow") else "revise", text=data.get("text", "")))
                self._notify_completed(task)
                if not data.get("allow"):
                    self.supervisor.enable(task["group_id"], task["agent_id"])
                return task
            if request["kind"] == "tool":
                response = {"allow": data.get("allow") is True}
            else:
                response = {"text": str(data.get("text", ""))[:16000]}
                if not response["text"].strip():
                    raise ValueError("请填写答复")
            with self.repo.transaction():
                self.attention.resolve(HUMAN, request["id"], response)
                if request["kind"] == "question":
                    self.messages.send(HUMAN, request["group_id"], dict(text="关于「%s」的答复：\n%s" % (request["title"], response["text"]), targets=[request["actor_id"]]), origin="human_answer")
            return True
        if op == "agent.clone":
            result = self.profiles.create(data)
            with self.repo.transaction():
                self.repo.emit("", "agent.created", "human", {"actor_id": result["id"], "source_id": result["source_id"]})
            return result
        if op == "permissions.configure":
            return self.permissions.configure(data)
        if op == "agent.save":
            affected = self.profiles.affected(data["id"])
            if any(r["actor_id"] in affected and r["status"] in ("running", "waiting", "starting") for r in self.repo.list("run")):
                raise Conflict("请先停止该成员及其分身的当前执行；仅修改权限可直接使用“工具权限”")
            if data.get("source_id"):
                self.profiles.validate_source(data["source_id"])
            else:
                self.registry.get(data["kind"])
                if len(affected) > 1:
                    current = self.config.agent(data["id"])
                    if current["kind"] != data["kind"] or (current["kind"] == "adp" and data.get("allow_personas") is not True):
                        raise ValueError("此接入已有分身，不能更换类型或关闭角色覆盖能力")
            for actor in self.repo.list("actor"):
                if actor["actor_id"] in affected:
                    self.supervisor.stop_actor(actor["group_id"], actor["actor_id"], suspend=False)
            result = self.config.save_agent(data)
            with self.repo.transaction():
                for actor in self.repo.list("actor"):
                    if actor["actor_id"] == data["id"]:
                        actor["mode"] = "external" if result["kind"] == "external" else "managed"
                        self.repo.put("actor", actor)
                self.repo.emit("", "agent.configured", "human", {"actor_id": data["id"]})
            return result
        if op == "agent.check":
            return self.registry.check(self.config.agent(data["id"]), self.config)
        if op == "connection.issue":
            return self.connection(data["group_id"], data["actor_id"], rotate=bool(data.get("rotate")))
        if op == "gateway.configure":
            return self.gateway.configure(data)
        if op == "run.get":
            from .runtime.progress import projected
            value = projected(self.repo.require("run", data["id"]))
            value.pop("prompt", None)
            return value
        if op == "session.action":
            gid, aid = data["group_id"], data["actor_id"]
            if data["action"] not in ("stop", "new", "start"):
                raise ValueError("未知会话操作")
            if data["action"] == "start":
                return self.supervisor.enable(gid, aid)
            self.supervisor.stop_actor(gid, aid)
            if data["action"] == "new":
                return self.sessions.new(gid, aid)
            return True
        if op == "events.list":
            return self.repo.events(data["group_id"], data.get("after", 0), data.get("limit", 100))
        raise ValueError("未知操作：" + op)

    def _notify_completed(self, task):
        if task["status"] != "done":
            return
        with self.repo.transaction():
            task = self.repo.require("task", task["id"])
            if task.get("notified"):
                return
            task["notified"] = True
            self.repo.put("task", task)
            group = self.repo.require("group", task["group_id"])
            if task["agent_id"] != group["leader"]:
                author = HUMAN if task.get("approved_by") == "human" else Principal(actor_id=task["agent_id"], group_id=group["id"])
                self.messages.send(author, group["id"], dict(targets=[group["leader"]], mode="send",
                    text="已确认交付：%s\n%s" % (task["title"], task["result"][:32000])), origin="task_review", root_id=task.get("root_id"))

    def connection(self, gid, aid, rotate=False):
        with self.connection_lock:
            return self._connection(gid, aid, rotate)

    def _connection(self, gid, aid, rotate):
        from .config import atomic_json, protect
        from .interfaces.mcp import command_for_connection
        if not self.endpoint:
            raise RuntimeError("协作服务尚未绑定地址")
        self.repo.require("actor", actor_key(gid, aid))
        if rotate and any(r["actor_id"] == aid and r["status"] in ("starting", "running", "waiting") for r in self.repo.list("run", gid)):
            raise Conflict("请先停止当前会话再轮换接入凭据")
        if rotate:
            self.supervisor.stop_actor(gid, aid, suspend=False)
        directory = self.config.root / "connections"
        path = directory / (gid + "-" + aid + ".json")
        old = json.loads(path.read_text("utf-8")) if path.exists() else None
        token = protect(old["protected_token"], True) if old and not rotate else self.access.issue(gid, aid)
        atomic_json(path, dict(endpoint=self.endpoint, group_id=gid, actor_id=aid, protected_token=protect(token)))
        command, args = command_for_connection(path)
        public_url = self.config.data.get("gateway", {}).get("public_url", "").rstrip("/")
        return dict(endpoint=self.endpoint + "/agent/v1", mcp_endpoint=self.endpoint + "/mcp", token=token,
                    group_id=gid, actor_id=aid, connection_file=str(path),
                    remote_endpoint=public_url + "/agent/v1" if public_url else "",
                    remote_mcp={"mcpServers": {"teams": {"type": "http", "url": public_url + "/mcp", "headers": {"Authorization": "Bearer " + token}}}} if public_url else None,
                    mcp_config={"mcpServers": {"teams": {"command": command, "args": args}}})

    def close(self):
        self.gateway.close()
        self.supervisor.close()
        self.repo.close()
