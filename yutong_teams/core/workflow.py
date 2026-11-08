"""One final acceptance per task chain; internal work is completed by agents."""
from .contracts import HUMAN, Conflict, Forbidden, now, require_text
from .lifecycle import current_work, require_open, settle_work_deliveries


class Workflow:
    def __init__(self, repo, access, attention, messages):
        self.repo, self.access, self.attention, self.messages = repo, access, attention, messages

    def submit(self, p, gid, values):
        with self.repo.transaction():
            group = self.access.group(p, gid)
            if p.actor_id != group["leader"] and not p.admin:
                raise Forbidden("由队长汇总内部评审后提交最终交付")
            root, epoch = current_work(self.repo, p, gid, values.get("work_id", ""))
            if not root:
                raise ValueError("请从共享上下文选择 work_id")
            work = self.repo.require("work", root)
            title = require_text(values.get("title"), "交付名称", 200)
            result = require_text(values.get("text"), "最终交付", 100000)
            if epoch != work["epoch"]:
                raise Conflict("这是旧修订轮次的回调，请重新读取最终交付状态")
            if work["status"] in ("review", "done") and work["result"] == result and work["title"] == title \
                    and values.get("version") in (work.get("submitted_from_version"), work["version"]):
                return work  # Lost-response retry, without a second acceptance request.
            require_open(self.repo, root, epoch)
            if values.get("version") != work["version"]:
                raise Conflict("最终交付已更新，请重新读取共享上下文")
            tasks = [t for t in self.repo.list("task", gid) if t["root_id"] == root]
            if any(t["status"] not in ("done", "cancelled") for t in tasks):
                raise Conflict("请先完成当前任务链的内部任务和评审，再提交最终交付")
            pending = [r for r in self.repo.list("request", gid) if r.get("root_id") == root and r["status"] == "pending"]
            if pending:
                raise Conflict("当前任务链还有未处理的人类提问或工具确认")
            for d in self.repo.list("delivery", gid):
                m = self.repo.require("message", d["message_id"])
                if m["root_id"] == root and m.get("work_epoch", 1) == work["epoch"] and d["recipient"] != "human" \
                        and d["mode"] != "mail" and d["state"] in ("queued", "offered", "uncertain", "failed") \
                        and m.get("origin") == "explicit" and not m.get("reply_to") and not d.get("read_at"):
                    raise Conflict("还有未处理的工作消息，请先核对收件箱和投递状态")
            work.update(title=title, result=result, status="review" if group["review"] else "done", submitted_from_version=work["version"],
                        version=work["version"] + 1, submitted=now(), submitted_by=p.actor_id,
                        task_ids=[t["id"] for t in tasks])
            self.repo.put("work", work)
            settle_work_deliveries(self.repo, work)
            if group["review"]:
                request = self.attention.create(p, gid, "final_review", ("确认最终交付：" + title)[:200], result,
                                                work_id=root, root_id=root, work_version=work["version"])
                work["request_id"] = request["id"]
                self.repo.put("work", work)
            message = dict(targets=["human"], text=result, mode="mail")
            original = self.repo.get("message", root)
            if original and original["author"] == "human" and p.actor_id in original["targets"]:
                message["reply_to"] = original["id"]
            self.messages.send(p, gid, message, origin="final_delivery", root_id=root)
            self.repo.emit(gid, "work.submitted", p.actor_id, work)
            return work

    def answer(self, request_id, allow, feedback=""):
        with self.repo.transaction():
            request = self.repo.require("request", request_id)
            work = self.repo.require("work", request["work_id"])
            if request["status"] != "pending" or work["status"] != "review" \
                    or request.get("work_version") != work["version"]:
                raise Conflict("这份最终交付已经处理或被新版本替代")
            if not allow:
                feedback = require_text(feedback, "修订要求", 16000)
            self.attention.resolve(HUMAN, request_id, {"allow": allow, "text": feedback})
            return self._transition(work, allow, feedback)

    def reopen(self, gid, work_id, version, feedback):
        with self.repo.transaction():
            work = self.repo.require("work", work_id)
            if work["group_id"] != gid:
                raise Forbidden("不能重新打开其他空间的交付")
            if work["status"] != "done" or version != work["version"]:
                raise Conflict("交付状态已改变，请刷新后重试")
            return self._transition(work, False, require_text(feedback, "修订要求", 16000))

    def _transition(self, work, allow, feedback):
        gid = work["group_id"]
        group = self.repo.require("group", gid)
        settle_work_deliveries(self.repo, work)
        work.update(status="done" if allow else "active", version=work["version"] + 1, feedback=feedback)
        if allow:
            work.update(accepted=now(), approved_by="human")
        else:
            work.update(epoch=work["epoch"] + 1, request_id="", approved_by="")
            budget = self.repo.get("budget", work["id"])
            if budget:
                budget["used"] = 0
                self.repo.put("budget", budget)
        self.repo.put("work", work)
        self.messages.send(HUMAN, gid, dict(targets=[group["leader"]], mode="mail" if allow else "send",
            text=("最终交付已确认，协作结束，无需回复：" + work["title"]) if allow else ("请按以下意见修订，完成内部评审后重新提交最终交付：\n" + feedback)),
            origin="final_acceptance" if allow else "work_revision", root_id=work["id"])
        self.repo.emit(gid, "work.approved" if allow else "work.reopened", "human", work)
        return work
