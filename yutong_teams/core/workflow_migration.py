"""Upgrade existing task reviews without inventing a human acceptance or replaying work."""
from .contracts import now
from .lifecycle import ensure_work, retire_task_deliveries, settle_work_deliveries


def upgrade(repo):
    if repo.get("meta", "final-delivery-v1"):
        return []
    completed = []
    with repo.transaction():
        for group in repo.list("group"):
            gid = group["id"]
            tasks = repo.list("task", gid)
            by_root = {}
            for task in tasks:
                root = task["root_id"]
                ensure_work(repo, gid, root, task["title"])
                by_root.setdefault(root, []).append(task)
                task.setdefault("dispatch_epoch", 1)
                task.setdefault("work_epoch", 1)
                task["workflow_version"] = 2
                if task["status"] == "review":
                    task.update(status="done", version=task["version"] + 1, completed_by=task["agent_id"], notified=False)
                    completed.append(task)
                    for request in repo.list("request", gid):
                        if request.get("task_id") == task["id"] and request["status"] == "pending":
                            request.update(status="superseded", response="internal_task_completed", resolved=now())
                            repo.put("request", request)
                    repo.emit(gid, "task.review_migrated", "system", {"task_id": task["id"], "status": "done"})
                if task["status"] in ("done", "cancelled"):
                    retire_task_deliveries(repo, task, "upgrade")
                repo.put("task", task)
            for root, chain in by_root.items():
                # Existing human approvals are historical evidence, not a newly
                # fabricated final-review click. Pending internal reviews above
                # never satisfy this rule.
                if chain and all(t["status"] == "done" and t.get("approved_by") == "human" for t in chain):
                    work = repo.require("work", root)
                    work.update(status="done", legacy=True, result=chain[-1]["result"],
                                task_ids=[t["id"] for t in chain], accepted_evidence="legacy_task_approvals")
                    repo.put("work", work)
                    settle_work_deliveries(repo, work)
                    repo.emit(gid, "work.legacy_closed", "system", {"work_id": root, "task_ids": work["task_ids"]})
        repo.put("meta", dict(id="final-delivery-v1", completed=now()))
    return completed
