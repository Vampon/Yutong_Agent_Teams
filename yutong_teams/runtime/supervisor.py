"""Session supervision and delivery dispatch, separate from collaboration rules.

Each membership owns one adapter/session. Never hold the database transaction
while waiting for a provider, tool approval, process exit or network call.
"""
import hashlib
import json
import logging
from pathlib import Path
import threading
import time
from ..core.access import actor_key
from ..core.contracts import HUMAN, Principal, Conflict, now, uid
from .processes import Cancelled
from .prompting import render
from .progress import apply as apply_progress


class Supervisor:
    def __init__(self, control):
        self.control, self.repo = control, control.repo
        self.closed = threading.Event()
        self.lock = threading.RLock()
        self.drivers, self.workers, self.stops = {}, {}, {}
        self.loop = None

    def recover_interrupted(self):
        with self.repo.transaction():
            for run in self.repo.list("run"):
                if run["status"] not in ("running", "waiting", "starting"):
                    continue
                run.update(status="interrupted", error="上次运行未确认结束；请核对后处理交付，不会自动重放", finished=now())
                self.repo.put("run", run)
                delivery = self.repo.require("delivery", run["delivery_id"])
                if not delivery["replied_at"]:
                    delivery.update(state="uncertain", error=run["error"], lease_until=0)
                    self.repo.put("delivery", delivery)
                task = self.repo.get("task", run.get("task_id", ""))
                if task and task["status"] in ("running", "queued"):
                    task.update(status="interrupted", error=run["error"], version=task["version"] + 1)
                    self.repo.put("task", task)
                self.repo.emit(run["group_id"], "run.interrupted", "system", {"run_id": run["id"]})
            for session in self.repo.list("session"):
                member = self.repo.require("actor", session["id"])
                session["state"] = "offline" if member["mode"] == "external" else "stopped"
                self.repo.put("session", session)
            for request in self.repo.list("request"):
                if request["kind"] == "tool" and request["status"] == "pending":
                    request["status"] = "expired"
                    self.repo.put("request", request)

    def start(self):
        self.loop = threading.Thread(target=self._loop, daemon=True, name="teams-supervisor")
        self.loop.start()

    def _loop(self):
        maintenance = 0
        while not self.closed.wait(.2):
            try:
                self.tick()
                if time.monotonic() > maintenance:
                    self.control.messages.expire_offers()
                    self.control.sessions.expire()
                    maintenance = time.monotonic() + 2
            except Exception:
                logging.exception("Supervisor tick failed")

    def _dispatch_tasks(self):
        for group in self.repo.list("group"):
            if group["paused"]:
                continue
            for task in self.repo.list("task", group["id"]):
                if task["status"] != "todo" or not task["auto_run"] or task.get("message_id"):
                    continue
                if any(self.repo.require("task", key)["status"] != "done" for key in task["depends_on"]):
                    continue
                text = "任务分配：%s\n%s\n补充要求：%s" % (task["title"], task["description"], task["feedback"])
                creator = task["created_by"]
                member = self.repo.get("actor", actor_key(group["id"], creator))
                if creator != "human" and (not member or not member["enabled"]):
                    creator = group["leader"]
                author = HUMAN if creator == "human" else Principal(actor_id=creator, group_id=group["id"])
                message = self.control.messages.send(author, group["id"], dict(targets=[task["agent_id"]], text=text,
                    mode="request_reply", task_id=task["id"], client_id="task-dispatch:" + task["id"] + ":" + str(task["version"])), origin="task_assignment", root_id=task.get("root_id"))
                task.update(message_id=message["id"], status="queued", version=task["version"] + 1)
                self.repo.put("task", task)
                self.repo.emit(group["id"], "task.dispatched", "system", {"task_id": task["id"], "message_id": message["id"]})

    def tick(self):
        if not self.control.endpoint or self.closed.is_set():
            return
        launches = []
        with self.repo.transaction():
            self._dispatch_tasks()
            active = [r for r in self.repo.list("run") if r["status"] in ("running", "waiting", "starting")]
            occupied = {actor_key(r["group_id"], r["actor_id"]) for r in active}
            for delivery in self.repo.list("delivery"):
                if len(active) >= int(self.control.config.data.get("parallel", 3)):
                    break
                if delivery["state"] != "queued" or delivery["mode"] == "mail" or delivery["recipient"] == "human":
                    continue
                gid, aid = delivery["group_id"], delivery["recipient"]
                group = self.repo.require("group", gid)
                key = actor_key(gid, aid)
                actor = self.repo.require("actor", key)
                session = self.repo.require("session", key)
                if group["paused"] or key in occupied or not actor["enabled"] or actor["mode"] != "managed" or session.get("suspended"):
                    continue
                message = self.repo.require("message", delivery["message_id"])
                budget = self.repo.get("budget", message["root_id"], dict(id=message["root_id"], group_id=gid, used=0))
                if budget["used"] >= group["max_turns"]:
                    if not delivery.get("budget_wait"):
                        delivery["budget_wait"] = True
                        self.repo.put("delivery", delivery)
                        self.repo.emit(gid, "delivery.budget_wait", "system", {"delivery_id": delivery["id"]})
                    continue
                budget["used"] += 1
                self.repo.put("budget", budget)
                agent = self.control.config.agent(aid)
                run = dict(id=uid(), group_id=gid, actor_id=aid, delivery_id=delivery["id"], message_id=message["id"],
                           root_id=message["root_id"], task_id=message.get("task_id", ""), status="starting",
                           generation=session["generation"], workspace=agent.get("cwd") or group["workspace"],
                           result="", error="", events=[], trace=[], preview="", created=now())
                delivery.update(state="offered", attempt=delivery["attempt"] + 1, lease_until=0, budget_wait=False)
                self.repo.put("delivery", delivery)
                self.repo.put("run", run)
                session.update(state="starting", error="")
                self.repo.put("session", session)
                if run["task_id"]:
                    task = self.repo.require("task", run["task_id"])
                    task.update(status="running", version=task["version"] + 1)
                    self.repo.put("task", task)
                self.repo.emit(gid, "run.started", aid, {"run_id": run["id"], "message_id": message["id"], "attempt": delivery["attempt"]})
                stop = threading.Event()
                with self.lock:
                    self.stops[key] = stop
                launches.append((run, agent, session, stop))
                active.append(run); occupied.add(key)
        for args in launches:
            key = actor_key(args[0]["group_id"], args[0]["actor_id"])
            thread = threading.Thread(target=self._execute, args=args, daemon=True, name="actor-" + args[0]["actor_id"])
            with self.lock:
                self.workers[key] = thread
            thread.start()

    def _driver(self, run, agent, session, p, persist):
        key = actor_key(run["group_id"], run["actor_id"])
        relevant = {k: agent.get(k) for k in ("kind", "command", "args", "project", "config_path", "url", "user_id", "auto_tools")}
        for key_name in ("dsh_config_path", "model_provider", "model"):
            if agent.get(key_name):
                relevant[key_name] = agent[key_name]
        relevant["workspace"] = str(Path(run["workspace"]).resolve())
        config_file = agent.get("config_path") or (str(Path(agent.get("project", "")) / "config.yaml") if agent["kind"] == "ccu" else "")
        if config_file and Path(config_file).is_file():
            relevant["config_hash"] = hashlib.sha256(Path(config_file).read_bytes()).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(relevant, sort_keys=True).encode()).hexdigest()
        if session.get("fingerprint") and session["fingerprint"] != fingerprint:
            raise Conflict("运行配置或工作目录已改变；请明确新建会话，原会话记录会保留")
        with self.lock:
            existing = self.drivers.get(key)
        if existing:
            return existing
        self.control.registry.check(agent, self.control.config)
        folder = self.control.config.root / "sessions" / run["group_id"] / run["actor_id"] / session["generation"]
        folder.mkdir(parents=True, exist_ok=True)
        connection = self.control.connection(run["group_id"], run["actor_id"])
        binding = dict(directory=folder, connection=connection, endpoint=self.control.endpoint, workspace=run["workspace"],
                       invoke=lambda op, data: self.control.agent_call(p, op, data))
        spec = self.control.registry.get(agent["kind"])
        persist(fingerprint=fingerprint)
        driver = spec.factory(self.control.config, agent, session, binding, persist)
        with self.lock:
            self.drivers[key] = driver
        return driver

    def _execute(self, run, agent, initial_session, stop):
        gid, aid = run["group_id"], run["actor_id"]
        key = actor_key(gid, aid)
        p = Principal(actor_id=aid, group_id=gid)
        accepted = False
        def persist(**fields):
            with self.repo.transaction():
                session = self.repo.require("session", key)
                if session["generation"] != run["generation"]:
                    raise Conflict("旧会话不能覆盖新会话")
                session.update(**fields)
                self.repo.put("session", session)
                self.repo.emit(gid, "session.updated", aid, {k: v for k, v in fields.items() if k != "fingerprint"})
        def emit(kind, data):
            nonlocal accepted
            if stop.is_set():
                return
            if kind == "accepted":
                if accepted:
                    return
                accepted = True
                self.control.messages.acknowledge(p, gid, run["message_id"], "delivered")
                persist(state="busy", last_seen=now())
                with self.repo.transaction():
                    current = self.repo.require("run", run["id"])
                    current["status"] = "running"
                    self.repo.put("run", current)
                return
            safe = self.control.config.redact(json.dumps(data, ensure_ascii=False, default=str))
            data = json.loads(safe)
            # Keep tool IDs/status even when a single result is large.
            for field, value in list(data.items()):
                encoded = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
                if len(encoded) > 16000:
                    data[field] = encoded[:16000]
                    data["truncated"] = True
            with self.repo.transaction():
                current = self.repo.require("run", run["id"])
                current["events"].append(dict(type=kind, data=data, time=now()))
                current["events"] = current["events"][-200:]
                if kind in ("text", "text_delta"):
                    current["preview"] = (current["preview"] + str(data.get("text", "")))[-12000:]
                elif kind == "text.replace":
                    current["preview"] = str(data.get("text", ""))[-12000:]
                apply_progress(current, kind, data)
                self.repo.put("run", current)
                self.repo.emit(gid, "run.progress", aid, {"run_id": run["id"], "type": kind})
        def approve(name, arguments):
            safe = json.loads(self.control.config.redact(json.dumps(arguments, ensure_ascii=False, default=str)))
            mode = self.control.permissions.mode(aid)
            if mode in ("auto", "deny"):
                allowed = mode == "auto" and not stop.is_set()
                emit("tool.permission", dict(tool=name, arguments=safe, policy=mode, allow=allowed))
                with self.repo.transaction():
                    self.repo.emit(gid, "tool.permission", "system", dict(actor_id=aid, run_id=run["id"], tool=name, policy=mode, allow=allowed))
                return allowed
            request = self.control.attention.create(p, gid, "tool", "确认工具执行：" + str(name)[:150],
                run_id=run["id"], tool=name, arguments=safe)
            emit("tool", dict(name=name, arguments=safe, status="awaiting_approval"))
            persist(state="waiting")
            with self.repo.transaction():
                current = self.repo.require("run", run["id"]); current["status"] = "waiting"; self.repo.put("run", current)
            deadline = time.monotonic() + 600
            try:
                while not stop.wait(.15):
                    answer = self.repo.require("request", request["id"])
                    mode = self.control.permissions.mode(aid)
                    if answer["status"] == "pending" and mode in ("auto", "deny"):
                        answer = self.control.attention.resolve_policy(request["id"], mode)
                    if answer["status"] != "pending":
                        allowed = answer["status"] == "resolved" and answer["response"].get("allow") is True
                        policy = (answer.get("response") or {}).get("policy", "human")
                        emit("tool.permission", dict(tool=name, allow=allowed, policy=policy))
                        return allowed
                    if time.monotonic() > deadline:
                        raise TimeoutError("等待工具确认超时")
                raise Cancelled("用户停止了等待确认的执行")
            finally:
                with self.repo.transaction():
                    answer = self.repo.require("request", request["id"])
                    if answer["status"] == "pending":
                        answer["status"] = "expired"; self.repo.put("request", answer)
                    current = self.repo.require("run", run["id"]); current["status"] = "running"; self.repo.put("run", current)
                persist(state="busy")
        try:
            driver = self._driver(run, agent, initial_session, p, persist)
            result = driver.run(render(self.control, run), run, stop, emit, approve)
            if stop.is_set():
                raise Cancelled("执行已停止")
            result = self.control.config.redact(str(result))
            if len(result) > 100000:
                raise ValueError("回复超过 100000 字符")
            spec = self.control.registry.get(agent["kind"])
            with self.repo.transaction():
                if spec.capabilities["auto_reply"]:
                    if not result.strip():
                        raise ValueError("适配器没有返回有效正文")
                    self.control.messages.send(p, gid, dict(reply_to=run["message_id"], text=result), origin="adapter_response")
                    if run["task_id"]:
                        task = self.repo.require("task", run["task_id"])
                        self.control.tasks.update(p, gid, task["id"], dict(version=task["version"], action="submit", text=result))
                current = self.repo.require("run", run["id"])
                current.update(status="completed", result=result, finished=now())
                self.repo.put("run", current)
                self.repo.emit(gid, "run.completed", aid, {"run_id": run["id"]})
                session = self.repo.require("session", key)
                if session["generation"] == run["generation"]:
                    session.update(state="ready", turns=session.get("turns", 0) + 1, last_seen=now(), error="")
                    self.repo.put("session", session)
                task = self.repo.get("task", run.get("task_id", ""))
                if task and task["status"] == "running":
                    task.update(status="blocked", error="运行已结束，成员尚未通过协作工具提交交付", version=task["version"] + 1)
                    self.repo.put("task", task)
            if task:
                self.control._notify_completed(task)
        except Exception as exc:
            error = self.control.config.redact(str(exc))
            cancelled = isinstance(exc, Cancelled) or stop.is_set()
            with self.repo.transaction():
                current = self.repo.require("run", run["id"])
                current.update(status="cancelled" if cancelled else "failed", error=error, finished=now())
                self.repo.put("run", current)
                delivery = self.repo.require("delivery", run["delivery_id"])
                if not delivery["replied_at"]:
                    delivery.update(state="uncertain", error=error)
                    self.repo.put("delivery", delivery)
                session = self.repo.require("session", key)
                if session["generation"] == run["generation"]:
                    session.update(state="stopped" if cancelled else "error", error=error, suspended=True)
                    self.repo.put("session", session)
                task = self.repo.get("task", run.get("task_id", ""))
                if task and task["status"] in ("running", "queued"):
                    task.update(status="interrupted" if cancelled else "failed", error=error, version=task["version"] + 1)
                    self.repo.put("task", task)
                self.repo.emit(gid, "run." + current["status"], aid, {"run_id": run["id"], "error": error})
            self._close_driver(key)
        finally:
            with self.lock:
                self.stops.pop(key, None)

    def _close_driver(self, key):
        with self.lock:
            driver = self.drivers.pop(key, None)
        if driver:
            driver.close()

    def enable(self, gid, aid):
        with self.repo.transaction():
            session = self.repo.require("session", actor_key(gid, aid))
            session.update(suspended=False, state="ready" if actor_key(gid, aid) in self.drivers else "stopped", error="")
            self.repo.put("session", session)
            self.repo.emit(gid, "session.enabled", "human", {"actor_id": aid})
            return session

    def stop_actor(self, gid, aid, suspend=True):
        key = actor_key(gid, aid)
        with self.repo.transaction():
            session = self.repo.require("session", key)
            session["suspended"] = True
            self.repo.put("session", session)
        with self.lock:
            stop, thread = self.stops.get(key), self.workers.get(key)
        if stop:
            stop.set()
        self._close_driver(key)
        if thread and thread is not threading.current_thread():
            thread.join(timeout=5)
            if thread.is_alive():
                raise Conflict("正在停止运行器，请稍后再操作会话")
        with self.repo.transaction():
            session = self.repo.require("session", key)
            session.update(state="stopped", suspended=suspend)
            self.repo.put("session", session)
            self.repo.emit(gid, "session.stopped", "human", {"actor_id": aid})

    def stop_group(self, gid):
        for actor in self.repo.list("actor", gid):
            if actor["mode"] == "managed":
                self.stop_actor(gid, actor["actor_id"], suspend=False)

    def cancel_task(self, task_id):
        for run in self.repo.list("run"):
            if run.get("task_id") == task_id and run["status"] in ("starting", "running", "waiting"):
                self.stop_actor(run["group_id"], run["actor_id"], suspend=False)

    def close(self):
        self.closed.set()
        if self.loop:
            self.loop.join(timeout=3)
        with self.lock:
            for stop in self.stops.values():
                stop.set()
            keys, threads = list(self.drivers), list(self.workers.values())
        for key in keys:
            self._close_driver(key)
        for thread in threads:
            thread.join(timeout=5)
