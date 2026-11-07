"""One-way import of 0.1 data. Keep the old DB untouched as a rollback copy."""
import json
import sqlite3
from .contracts import now, uid


def import_v1(repo, root):
    old = root / "teams.db"
    if not old.exists() or repo.get("meta", "v1-import") or repo.list("group"):
        return
    db = sqlite3.connect("file:" + old.as_posix() + "?mode=ro", uri=True)
    try:
        row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
        data = json.loads(row[0]) if row else {}
    finally:
        db.close()
    with repo.transaction():
        for old_group in data.get("groups", []):
            gid = old_group["id"]
            if gid == "worker":
                continue
            group = {k: old_group[k] for k in ("id", "name", "workspace", "leader", "review", "max_turns", "created")}
            group.update(group_id=gid, paused=True)
            repo.put("group", group)
            repo.put("context", dict(id=gid, group_id=gid, version=1, brief=old_group.get("goal", ""), decisions=[], handoffs=[], constraints=[]))
            for aid in old_group["members"]:
                key = gid + ":" + aid
                repo.put("actor", dict(id=key, group_id=gid, actor_id=aid, enabled=True, mode="managed", created=now()))
                repo.put("session", dict(id=key, group_id=gid, actor_id=aid, generation=uid(), provider_id="", state="stopped", fingerprint="", last_seen="", error="", started="", turns=0))
            for item in old_group["messages"]:
                author = "human" if item["author"] == "user" else item["author"]
                message = dict(id=item["id"], group_id=gid, author=author, text=item["text"], targets=item.get("targets", []),
                               mode="send", reply_to="", root_id=item["id"], time=item["time"], origin="legacy-v0.1", task_id=item.get("task_id", ""))
                repo.put("message", message)
                # v0.1 job statuses cannot prove read/delivery facts; do not invent receipts.
            for item in old_group["tasks"]:
                task = dict(item, group_id=gid, version=1, auto_run=False, message_id="", created_by="human",
                            feedback=item.get("feedback", ""), error=item.get("error", ""), root_id=uid())
                if task["status"] in ("running", "queued", "held", "waiting"):
                    task.update(status="interrupted", error="旧版未完成任务已保留，请核对结果后手动重试")
                repo.put("task", task)
            repo.emit(gid, "migration.imported", "system", {"source": "v0.1", "messages": len(old_group["messages"]), "tasks": len(old_group["tasks"]), "paused": True})
        repo.put("meta", {"id": "v1-import", "group_id": "", "completed": now(), "source": str(old)})
