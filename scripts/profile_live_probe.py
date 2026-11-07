"""Bounded real Claude persona/session/peer-tool probe in an isolated user home."""
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config, atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve


def main():
    root = Path(__file__).resolve().parents[1] / ".test-data" / ("profiles-live-" + uuid.uuid4().hex[:8])
    config = Config(root)
    c = Coordinator(config)
    server, _ = serve(c)
    report = {"home": str(root), "checks": [], "ok": False}
    try:
        reviewer = c.admin_call("agent.clone", dict(id="requirements", source_id="claude", name="需求评审", role="需求评审",
            instructions="你的专属职责是需求评审，职责代号 REVIEW。仅使用协作工具，不读写文件、不执行终端命令。", permission_mode="deny", timeout=180))
        developer = c.admin_call("agent.clone", dict(id="developer", source_id="claude", name="代码开发", role="代码开发",
            instructions="你的专属职责是代码开发，职责代号 DEVELOP。仅使用协作工具，不读写文件、不执行终端命令。", permission_mode="deny", timeout=180))
        group = c.admin_call("group.create", dict(name="双 Claude 分身实测", members=[reviewer["id"], developer["id"]],
            workspace=str(root), review=False, max_turns=10, goal="验证独立职责、私有会话记忆和成员之间的协作工具"))
        gid = group["id"]

        def send(aid, text):
            return c.admin_call("message.send", dict(group_id=gid, targets=[aid], mode="request_reply", text=text))

        def wait(messages):
            deadline = time.monotonic() + 220
            ids = {m["id"] for m in messages}
            while time.monotonic() < deadline:
                runs = [r for r in c.repo.list("run", gid) if r["message_id"] in ids]
                if any(r["status"] in ("failed", "cancelled") for r in runs):
                    raise RuntimeError("运行失败：" + json.dumps([{k: r.get(k) for k in ("actor_id", "status", "error")} for r in runs], ensure_ascii=False))
                deliveries = [d for d in c.repo.list("delivery", gid) if d["message_id"] in ids]
                if len(runs) == len(ids) and all(r["status"] == "completed" for r in runs) and all(d["replied_at"] for d in deliveries):
                    return
                time.sleep(.2)
            raise TimeoutError("真实分身验收超时")

        markers = {"requirements": "R-" + uuid.uuid4().hex[:10], "developer": "D-" + uuid.uuid4().hex[:10]}
        first = [send(aid, "请记住仅属于你当前会话的口令：%s。读取本次收件箱，使用 teams_reply 向我回复你的职责代号和口令。不要读取历史消息，不调用其他成员。" % marker)
                 for aid, marker in markers.items()]
        wait(first)
        sessions = {aid: c.repo.require("session", gid + ":" + aid)["provider_id"] for aid in markers}
        assert all(sessions.values()) and len(set(sessions.values())) == 2, "原生会话未隔离"
        report["checks"].append("two distinct native Claude sessions")
        second = [send(aid, "只凭当前原生会话的记忆，回复刚才让你记住的口令和你自己的职责代号。不得通过 message_history/context 读取旧消息，也不要询问同伴；仅调用 inbox_read 和 reply。") for aid in markers]
        wait(second)
        for m, (aid, marker) in zip(second, markers.items()):
            replies = [x for x in c.repo.list("message", gid) if x["reply_to"] == m["id"] and x["author"] == aid]
            text = "\n".join(x["text"] for x in replies)
            assert marker in text and all(other not in text for key, other in markers.items() if key != aid), "会话记忆串线"
            assert ("REVIEW" if aid == "requirements" else "DEVELOP") in text, "专属职责未应用"
            assert sessions[aid] == c.repo.require("session", gid + ":" + aid)["provider_id"], "未复用原生会话"
        report["checks"].append("independent persona instructions and second-turn memory")
        third = send("requirements", "用 teams_send 向 developer 发一条 request_reply：请它只用 teams_reply(mode=mail) 回复自己的职责代号 DEVELOP。你向我回复已委派即可，不要等待它回复，不要发送私有口令。")
        wait([third])
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            peer = [m for m in c.repo.list("message", gid) if m["author"] == "requirements" and "developer" in m["targets"]]
            replies = [m for m in c.repo.list("message", gid) if m["author"] == "developer" and m["reply_to"] in {p["id"] for p in peer}]
            if replies and not any(r["status"] in ("running", "starting", "waiting") for r in c.repo.list("run", gid)):
                assert "DEVELOP" in replies[-1]["text"]
                report["checks"].append("real peer message and reply between two Claude personas")
                break
            time.sleep(.2)
        else:
            raise TimeoutError("未观察到分身之间真实回复")
        report["ok"] = True
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        report["runs"] = [{k: r.get(k) for k in ("actor_id", "status", "error")} for r in c.repo.list("run")]
        report["sessions"] = [{k: s.get(k) for k in ("actor_id", "provider_id", "turns")} for s in c.repo.list("session")]
        server.shutdown()
        server.server_close()
        c.close()
        atomic_json(root / "report.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
