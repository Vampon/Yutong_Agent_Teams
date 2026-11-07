import hashlib
import secrets
from .contracts import Forbidden, Principal, now, uid


def actor_key(group_id, actor_id):
    return group_id + ":" + actor_id


class Access:
    def __init__(self, repo):
        self.repo = repo

    def group(self, principal, group_id):
        group = self.repo.require("group", group_id)
        if not principal.admin:
            if principal.group_id != group_id:
                raise Forbidden("不能访问其他协作空间")
            member = self.repo.require("actor", actor_key(group_id, principal.actor_id))
            if not member["enabled"]:
                raise Forbidden("成员已停用")
        return group

    def manager(self, principal, group_id):
        group = self.group(principal, group_id)
        if not principal.admin and group["leader"] != principal.actor_id:
            raise Forbidden("此操作需要队长或人类管理员")
        return group

    def issue(self, group_id, actor_id):
        self.repo.require("actor", actor_key(group_id, actor_id))
        token = secrets.token_urlsafe(40)
        with self.repo.transaction():
            # One token per membership; reissuing revokes earlier connections.
            record = dict(id=actor_key(group_id, actor_id), group_id=group_id,
                          actor_id=actor_id, digest=hashlib.sha256(token.encode()).hexdigest(), issued=now())
            self.repo.put("credential", record)
            self.repo.emit(group_id, "actor.credential_issued", "human", {"actor_id": actor_id})
        return token

    def authenticate(self, token):
        if not token:
            raise Forbidden("缺少成员凭据")
        digest = hashlib.sha256(token.encode()).hexdigest()
        for item in self.repo.list("credential"):
            if secrets.compare_digest(item["digest"], digest):
                p = Principal(actor_id=item["actor_id"], group_id=item["group_id"])
                self.group(p, p.group_id)
                return p
        raise Forbidden("成员凭据无效或已撤销")
