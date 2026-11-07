"""Durable member identity and resumable provider-session metadata."""
import time
from .access import actor_key
from .contracts import now, uid, Forbidden


class Sessions:
    def __init__(self, repo, access):
        self.repo, self.access = repo, access

    def connect(self, p, gid, details):
        self.access.group(p, gid)
        with self.repo.transaction():
            member = self.repo.require("actor", actor_key(gid, p.actor_id))
            if member["mode"] != "external":
                raise Forbidden("此成员由工作台管理；请为外部系统创建独立成员")
            session = self.repo.require("session", member["id"])
            session.update(state="ready", last_seen=now(), heartbeat=time.time(), error="",
                           provider_id=str(details.get("session_id", session["provider_id"]))[:200],
                           client=str(details.get("client", "External agent"))[:100],
                           reported_capabilities=details.get("capabilities", {}))
            self.repo.put("session", session)
            self.repo.emit(gid, "session.connected", p.actor_id, {"client": session["client"]})
            return session

    def heartbeat(self, p, gid):
        self.access.group(p, gid)
        with self.repo.transaction():
            session = self.repo.require("session", actor_key(gid, p.actor_id))
            session.update(last_seen=now(), heartbeat=time.time())
            if session["state"] in ("offline", "stopped"):
                session["state"] = "ready"
                self.repo.emit(gid, "session.online", p.actor_id, {})
            self.repo.put("session", session)
            return {"online": True, "group_paused": self.repo.require("group", gid)["paused"]}

    def new(self, gid, aid):
        with self.repo.transaction():
            session = self.repo.require("session", actor_key(gid, aid))
            self.repo.emit(gid, "session.retired", "human", {"actor_id": aid, "provider_id": session["provider_id"], "generation": session["generation"]})
            session.update(generation=uid(), provider_id="", state="stopped", fingerprint="", error="", turns=0, started="", suspended=False,
                           model="", model_provider="", model_source="")
            self.repo.put("session", session)
            return session

    def status(self, p, gid, values):
        self.access.group(p, gid)
        with self.repo.transaction():
            record = dict(id=actor_key(gid, p.actor_id), group_id=gid, actor_id=p.actor_id,
                          focus=str(values.get("focus", ""))[:4000], blocked=str(values.get("blocked", ""))[:4000], updated=now())
            self.repo.put("actor_context", record)
            self.repo.emit(gid, "actor.status_updated", p.actor_id, record)
            return record

    def expire(self):
        with self.repo.transaction():
            for actor in self.repo.list("actor"):
                if actor["mode"] != "external":
                    continue
                session = self.repo.require("session", actor["id"])
                if session["state"] == "ready" and time.time() - session.get("heartbeat", 0) > 90:
                    session["state"] = "offline"
                    self.repo.put("session", session)
                    self.repo.emit(actor["group_id"], "session.offline", actor["actor_id"], {})
