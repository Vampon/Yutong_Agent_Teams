"""Human participation is explicit durable state, not text pattern matching."""
from .contracts import Forbidden, Conflict, now, uid, require_text


class Attention:
    def __init__(self, repo, access):
        self.repo, self.access = repo, access

    def create(self, p, gid, kind, title, detail="", **fields):
        self.access.group(p, gid)
        with self.repo.transaction():
            request = dict(id=uid(), group_id=gid, actor_id=p.actor_id, kind=kind,
                           title=require_text(title, "标题", 200), detail=str(detail)[:16000],
                           status="pending", response=None, created=now(), **fields)
            self.repo.put("request", request)
            self.repo.emit(gid, "human.requested", p.actor_id, {"request_id": request["id"], "kind": kind, "title": title})
            return request

    def resolve(self, p, request_id, response):
        if not p.admin:
            raise Forbidden("只有人类可以处理确认事项")
        with self.repo.transaction():
            request = self.repo.require("request", request_id)
            if request["status"] != "pending":
                raise Conflict("此事项已经处理")
            request.update(status="resolved", response=response, resolved=now())
            self.repo.put("request", request)
            self.repo.emit(request["group_id"], "human.responded", "human", {"request_id": request_id, "response": response})
            return request

    def resolve_policy(self, request_id, mode):
        """A changed human policy may resolve a waiting tool request atomically."""
        if mode not in ("auto", "deny"):
            raise ValueError("策略尚未作出执行决定")
        with self.repo.transaction():
            request = self.repo.require("request", request_id)
            if request["kind"] != "tool":
                raise Forbidden("工具策略不能处理业务提问或交付审核")
            if request["status"] != "pending":
                return request  # A human response that won the race remains authoritative.
            response = {"allow": mode == "auto", "policy": mode}
            request.update(status="resolved", response=response, resolved=now())
            self.repo.put("request", request)
            self.repo.emit(request["group_id"], "tool.permission", "system",
                           {"request_id": request_id, "actor_id": request["actor_id"], **response})
            return request
