"""CCCC-style delivery facts: send, request-reply and non-interrupting Mail.

Transport acceptance, explicit reading and an actual correlated reply are
recorded independently. Finishing a process never fabricates a read receipt.
"""
import time
from .contracts import MESSAGE_MODES, Forbidden, Conflict, require_text, now, uid


class Messaging:
    def __init__(self, repo, access):
        self.repo, self.access = repo, access

    def _targets(self, group, principal, targets):
        roster = [a["actor_id"] for a in self.repo.list("actor", group["id"]) if a["enabled"]]
        result = []
        if isinstance(targets, str):
            targets = [targets]
        if not isinstance(targets, list) or len(targets) > 100:
            raise ValueError("接收成员必须为数组")
        for target in targets:
            if target in ("all", "@all"):
                result.extend(a for a in roster if a != principal.actor_id)
            elif target == "@peers":
                result.extend(a for a in roster if a not in (principal.actor_id, group["leader"]))
            elif target == "@foreman":
                result.append(group["leader"])
            else:
                result.append("human" if target in ("user", "@human") else target)
        result = list(dict.fromkeys(result))
        if not result or any(a not in roster + ["human"] for a in result):
            raise ValueError("接收者必须是当前协作成员或 human")
        return result

    def send(self, p, gid, values, origin="explicit", root_id=None):
        with self.repo.transaction():
            group = self.access.group(p, gid)
            text = require_text(values.get("text"), "消息", 100000)
            mode = values.get("mode", "send")
            if mode not in MESSAGE_MODES:
                raise ValueError("发送方式应为 send、request_reply 或 mail")
            reply_to = values.get("reply_to", "")
            original = self.repo.require("message", reply_to) if reply_to else None
            if original and original["group_id"] != gid:
                raise Forbidden("不能跨空间回复")
            if original and not p.admin and p.actor_id not in original["targets"]:
                raise Forbidden("只能回复发给自己的消息")
            default = [original["author"]] if original else [group["leader"]]
            targets = self._targets(group, p, values.get("targets") or default)
            if original and original["author"] not in targets:
                raise ValueError("回复必须包含原消息发送者")
            fingerprint = dict(text=text, mode=mode, targets=targets, reply_to=reply_to)

            def commit():
                mid = uid()
                active = [r for r in self.repo.list("run", gid) if r["actor_id"] == p.actor_id and r["status"] in ("running", "waiting", "starting")]
                root = root_id or (original["root_id"] if original else (active[-1]["root_id"] if active else mid))
                message = dict(id=mid, group_id=gid, author=p.actor_id, text=text, mode=mode, targets=targets,
                               reply_to=reply_to, root_id=root, time=now(), origin=origin,
                               task_id=values.get("task_id", ""))
                self.repo.put("message", message)
                self.repo.emit(gid, "chat.message", p.actor_id, message)
                for target in targets:
                    delivery = dict(id=mid + ":" + target, group_id=gid, message_id=mid, recipient=target,
                                    state="queued", mode=mode, delivered_at="", read_at="", replied_at="",
                                    reply_ids=[], attempt=0, lease_until=0, error="", created=now())
                    self.repo.put("delivery", delivery)
                if original:
                    delivery = self.repo.get("delivery", original["id"] + ":" + p.actor_id)
                    if delivery:
                        delivery["replied_at"] = now()
                        delivery["reply_ids"].append(mid)
                        self.repo.put("delivery", delivery)
                        self.repo.emit(gid, "message.replied", p.actor_id, {"message_id": original["id"], "reply_id": mid})
                return message

            return self.repo.idempotent("message:" + gid + ":" + p.actor_id, values.get("client_id", ""), fingerprint, commit)

    def inbox(self, p, gid, limit=50, claim=False, unread=True):
        self.access.group(p, gid)
        with self.repo.transaction():
            rows = [d for d in self.repo.list("delivery", gid) if d["recipient"] == p.actor_id
                    and d["state"] not in ("dismissed", "cancelled")
                    and (not unread or not d["read_at"])]
            items = []
            for delivery in rows:
                if claim and delivery["state"] != "queued":
                    continue
                if claim and self.repo.require("group", gid)["paused"]:
                    continue
                if claim:
                    delivery.update(state="offered", lease_until=time.time() + 60, attempt=delivery["attempt"] + 1)
                    self.repo.put("delivery", delivery)
                    self.repo.emit(gid, "message.offered", p.actor_id, {"message_id": delivery["message_id"], "attempt": delivery["attempt"]})
                items.append(dict(message=self.repo.require("message", delivery["message_id"]), delivery=delivery))
                if len(items) >= min(100, max(1, int(limit))):
                    break
            return items

    def acknowledge(self, p, gid, message_id, stage):
        if stage not in ("delivered", "read"):
            raise ValueError("确认类型只能为 delivered 或 read")
        with self.repo.transaction():
            self.access.group(p, gid)
            delivery = self.repo.require("delivery", message_id + ":" + p.actor_id)
            if delivery["group_id"] != gid:
                raise Forbidden("不能确认其他空间的消息")
            field = stage + "_at"
            if delivery[field]:
                return delivery
            delivery[field] = now()
            if stage == "read" and not delivery["delivered_at"]:
                delivery["delivered_at"] = now()
                self.repo.emit(gid, "message.delivered", p.actor_id, {"message_id": message_id, "evidence": "explicit_read"})
            delivery.update(state="delivered", lease_until=0, error="")
            self.repo.put("delivery", delivery)
            self.repo.emit(gid, "message." + stage, p.actor_id, {"message_id": message_id})
            return delivery

    def read_inbox(self, p, gid, message_ids=None):
        with self.repo.transaction():
            self.access.group(p, gid)
            if message_ids is None:
                items = self.inbox(p, gid, unread=True)
            else:
                if not isinstance(message_ids, list) or len(message_ids) > 100 or not all(isinstance(x, str) for x in message_ids):
                    raise ValueError("每次最多读取 100 个消息 ID")
                items = []
                for mid in dict.fromkeys(message_ids):
                    delivery = self.repo.require("delivery", mid + ":" + p.actor_id)
                    if delivery["group_id"] != gid:
                        raise Forbidden("不能读取其他空间的收件箱")
                    if delivery["state"] == "dismissed":
                        continue
                    items.append(dict(message=self.repo.require("message", mid), delivery=delivery))
            for item in items:
                item["delivery"] = self.acknowledge(p, gid, item["message"]["id"], "read")
            return items

    def recover(self, gid, delivery_id, action):
        with self.repo.transaction():
            d = self.repo.require("delivery", delivery_id)
            if d["group_id"] != gid or d["state"] not in ("uncertain", "failed", "cancelled"):
                raise ValueError("只有不确定或失败的交付可进行恢复")
            if action not in ("retry", "dismiss"):
                raise ValueError("无效恢复方式")
            d.update(state="queued" if action == "retry" else "dismissed", lease_until=0, error="")
            self.repo.put("delivery", d)
            self.repo.emit(gid, "message.recovery_decided", "human", {"delivery_id": d["id"], "action": action})
            return d

    def expire_offers(self):
        with self.repo.transaction():
            for d in self.repo.list("delivery"):
                if d["state"] == "offered" and d["lease_until"] and d["lease_until"] < time.time():
                    d.update(state="uncertain", error="接收端领取后没有确认；请核对后决定是否重发", lease_until=0)
                    self.repo.put("delivery", d)
                    self.repo.emit(d["group_id"], "message.uncertain", "system", {"delivery_id": d["id"]})
