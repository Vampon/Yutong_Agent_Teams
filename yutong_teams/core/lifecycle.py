"""Task-chain identity and delivery eligibility shared by native and external runners.

Reading a message, running a task and accepting a final deliverable are separate
facts. Only current assignments may start work; obsolete deliveries never reopen it.
"""
from .contracts import Conflict, Forbidden, now

ACTIVE_RUNS = ("starting", "running", "waiting")


def ensure_work(repo, gid, root_id, title=""):
    work = repo.get("work", root_id)
    if work:
        if work["group_id"] != gid:
            raise Forbidden("不能使用其他空间的任务链")
        return work
    work = dict(id=root_id, group_id=gid, title=title[:200] or "协作任务",
                status="active", version=1, epoch=1, result="", created=now())
    repo.put("work", work)
    return work


def current_work(repo, p, gid, explicit=""):
    active = [r for r in repo.list("run", gid)
              if r["actor_id"] == p.actor_id and r["status"] in ACTIVE_RUNS]
    if active:
        run = active[-1]
        if explicit and explicit != run["root_id"]:
            raise Conflict("本次执行不能切换到另一条任务链")
        return run["root_id"], run.get("work_epoch", 1)
    if explicit:
        work = repo.require("work", explicit)
        if work["group_id"] != gid:
            raise Forbidden("不能使用其他空间的任务链")
        return explicit, work["epoch"]
    return "", None


def require_open(repo, root_id, epoch=None):
    work = repo.get("work", root_id)
    if work and (work["status"] != "active" or epoch is not None and epoch != work["epoch"]):
        raise Conflict("该轮协作已提交或结束；请查看最终交付，修订需要人类明确重新打开")
    return work


def retire_task_deliveries(repo, task, reason):
    for delivery in repo.list("delivery", task["group_id"]):
        message = repo.require("message", delivery["message_id"])
        if message.get("task_id") == task["id"] and message.get("origin") == "task_assignment" \
                and delivery["state"] in ("queued", "offered", "uncertain", "failed"):
            delivery.update(state="dismissed", lease_until=0, budget_wait=False, superseded_reason=reason)
            repo.put("delivery", delivery)
            repo.emit(task["group_id"], "message.task_superseded", "system",
                      {"delivery_id": delivery["id"], "reason": reason})


def obsolete_reason(repo, message):
    work = repo.get("work", message["root_id"])
    if work and (work["status"] != "active" or message.get("work_epoch", 1) != work["epoch"]):
        return "任务链已提交、结束或进入新的修订轮次"
    if message.get("origin") == "task_assignment":
        task = repo.get("task", message.get("task_id", ""))
        if not task or task["status"] != "queued" or task.get("message_id") != message["id"] \
                or task.get("dispatch_epoch", 1) != message.get("dispatch_epoch", 1):
            return "任务分配已被处理或替代"
    return ""


def eligible(repo, delivery):
    """Call inside the same transaction that claims/starts this delivery."""
    if delivery["state"] != "queued":
        return False
    message = repo.require("message", delivery["message_id"])
    reason = obsolete_reason(repo, message)
    if reason and delivery["mode"] != "mail":
        if message.get("origin") == "task_assignment":
            delivery.update(state="dismissed", lease_until=0)
        else:
            delivery.update(mode="mail", wake_suppressed=reason, budget_wait=False)
        repo.put("delivery", delivery)
        repo.emit(delivery["group_id"], "delivery.wake_suppressed", "system",
                  {"delivery_id": delivery["id"], "reason": reason})
    return delivery["state"] == "queued" and delivery["mode"] != "mail" and not reason


def settle_work_deliveries(repo, work):
    for delivery in repo.list("delivery", work["group_id"]):
        message = repo.require("message", delivery["message_id"])
        if message["root_id"] != work["id"] or delivery["recipient"] == "human":
            continue
        if message.get("origin") == "task_assignment" and delivery["state"] in ("queued", "offered", "uncertain", "failed"):
            delivery.update(state="dismissed", lease_until=0, budget_wait=False)
        else:
            # Preserve the content and true read/reply receipts as quiet inbox mail.
            delivery.update(mode="mail", lease_until=0, budget_wait=False, wake_suppressed="最终交付已提交")
        repo.put("delivery", delivery)
