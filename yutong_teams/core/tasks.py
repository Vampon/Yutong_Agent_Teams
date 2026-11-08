"""Durable assignments, dependency validation, ownership and human review."""
from .contracts import Conflict, Forbidden, now, uid, require_text
from .lifecycle import ensure_work, current_work, require_open, retire_task_deliveries


def validate_graph(tasks):
    table = {t["id"]: t for t in tasks}
    visited, pending = set(), set()
    def visit(key):
        if key in pending:
            raise ValueError("任务依赖不能形成循环")
        if key in visited:
            return
        if key not in table:
            raise ValueError("前置任务不存在")
        pending.add(key)
        for dependency in table[key]["depends_on"]:
            visit(dependency)
        pending.remove(key)
        visited.add(key)
    for key in table:
        visit(key)


class Tasks:
    def __init__(self, repo, access, attention):
        self.repo, self.access, self.attention = repo, access, attention

    def create(self, p, gid, values):
        with self.repo.transaction():
            group = self.access.group(p, gid)
            owner = values.get("agent_id") or p.actor_id
            member = self.repo.get("actor", gid + ":" + owner)
            if not member or not member["enabled"]:
                raise ValueError("负责人必须是当前协作成员")
            # A peer may delegate work, but may not edit another member's result.
            deps = values.get("depends_on", [])
            if not isinstance(deps, list) or not all(isinstance(x, str) for x in deps):
                raise ValueError("前置依赖应为任务 ID 数组")
            values = dict(values, agent_id=owner, depends_on=list(dict.fromkeys(deps)))
            def commit():
                tasks = self.repo.list("task", gid)
                if len(tasks) >= 500:
                    raise ValueError("每个协作最多 500 项任务")
                root, epoch = current_work(self.repo, p, gid, values.get("work_id", ""))
                if not root and deps:
                    root = self.repo.require("task", deps[0])["root_id"]
                if not root and not p.admin:
                    candidates = [w for w in self.repo.list("work", gid) if w["status"] == "active"]
                    if len(candidates) > 1:
                        raise ValueError("存在多条任务链，请指定 work_id")
                    root = candidates[0]["id"] if candidates else ""
                root = root or uid()
                work = ensure_work(self.repo, gid, root, values.get("title", ""))
                require_open(self.repo, root, epoch)
                task = dict(id=uid(), group_id=gid, root_id=root, title=require_text(values.get("title"), "任务名称", 200),
                            description=str(values.get("description", ""))[:32000], agent_id=owner,
                            depends_on=values["depends_on"], status="todo", result="", feedback="", error="",
                            auto_run=bool(values.get("auto_run", not p.admin)), version=1,
                            created=now(), created_by=p.actor_id, message_id="", dispatch_epoch=1,
                            workflow_version=2, work_epoch=work["epoch"])
                validate_graph(tasks + [task])
                self.repo.put("task", task)
                self.repo.emit(gid, "task.created", p.actor_id, task)
                return task
            return self.repo.idempotent("task:" + gid + ":" + p.actor_id, values.get("client_id", ""), values, commit)

    def update(self, p, gid, tid, values):
        with self.repo.transaction():
            group = self.access.group(p, gid)
            task = self.repo.require("task", tid)
            if task["group_id"] != gid:
                raise Forbidden("不能修改其他空间的任务")
            if values.get("version") != task["version"]:
                raise Conflict("任务已更新，请刷新后重试")
            action = values.get("action")
            if action in ("start", "progress", "block", "submit", "assign", "retry", "revise", "cancel"):
                _, epoch = current_work(self.repo, p, gid, task["root_id"])
                require_open(self.repo, task["root_id"], epoch)
            if action in ("retry", "revise", "start", "assign") and any(r.get("task_id") == tid and r["status"] in ("starting", "running", "waiting") for r in self.repo.list("run", gid)):
                raise Conflict("当前任务的运行器尚未退出，请先停止该成员")
            manager = p.admin or group["leader"] == p.actor_id
            owner = p.actor_id == task["agent_id"]
            if action in ("submit", "progress", "block") and not (owner or p.admin):
                raise Forbidden("只能报告自己负责的任务")
            if action in ("start", "cancel", "assign", "retry") and not (manager or owner):
                raise Forbidden("需要负责人、队长或人类管理员")
            if action in ("approve", "revise") and not p.admin:
                raise Forbidden("交付审核需要人类处理")
            if action == "start":
                if task["status"] not in ("todo", "blocked"):
                    raise Conflict("当前任务不可启动")
                task.update(auto_run=True, status="todo", error="", message_id="")
                task["dispatch_epoch"] = task.get("dispatch_epoch", 1) + 1
            elif action == "progress":
                if task["status"] in ("review", "done", "cancelled"):
                    raise Conflict("当前任务不能继续执行")
                if any(self.repo.require("task", d)["status"] != "done" for d in task["depends_on"]):
                    raise Conflict("前置交付尚未完成")
                task["status"] = "running"
            elif action == "block":
                if task["status"] in ("done", "cancelled"):
                    raise Conflict("已结束任务不能被阻塞")
                task.update(status="blocked", error=require_text(values.get("text"), "受阻原因", 10000))
            elif action == "submit":
                if task["status"] in ("done", "cancelled", "review"):
                    raise Conflict("当前任务不能再次交付")
                if any(self.repo.require("task", d)["status"] != "done" for d in task["depends_on"]):
                    raise Conflict("前置任务尚未完成")
                task.update(result=require_text(values.get("text"), "交付结果", 100000), error="",
                            status="done", completed_by=p.actor_id, completed=now())
            elif action == "approve":
                if task["status"] != "review":
                    raise Conflict("任务不在待审核状态")
                task["status"] = "done"
                task["approved_by"] = "human"
            elif action in ("revise", "retry"):
                if task["status"] not in ("review", "failed", "interrupted", "blocked", "cancelled", "done"):
                    raise Conflict("请先停止当前任务，再重试")
                task.update(status="todo", feedback=str(values.get("text", ""))[:10000], auto_run=True,
                            message_id="", error="", notified=False, approved_by="",
                            dispatch_epoch=task.get("dispatch_epoch", 1) + 1)
                work = self.repo.get("work", task["root_id"])
                if work:
                    task["work_epoch"] = work["epoch"]
            elif action == "cancel":
                task["status"] = "cancelled"
            elif action == "assign":
                if task["status"] not in ("todo", "blocked"):
                    raise Conflict("只能调整未执行任务的负责人")
                member = self.repo.require("actor", gid + ":" + values["agent_id"])
                if not member["enabled"]:
                    raise ValueError("成员已停用")
                task["agent_id"] = values["agent_id"]
            else:
                raise ValueError("未知任务操作")
            task["version"] += 1
            if action in ("retry", "revise", "start", "cancel", "submit", "approve", "progress", "block"):
                retire_task_deliveries(self.repo, task, action)
            self.repo.put("task", task)
            self.repo.emit(gid, "task." + action, p.actor_id, {"task_id": tid, "version": task["version"], "status": task["status"]})
            if action in ("approve", "revise", "cancel"):
                for request in self.repo.list("request", gid):
                    if request.get("task_id") == tid and request["status"] == "pending":
                        request.update(status="resolved", response=action, resolved=now())
                        self.repo.put("request", request)
            return task
