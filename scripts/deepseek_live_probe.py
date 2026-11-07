"""Real Harness route, collaboration and restart/resume acceptance.

Uses the user's selected model and credential references, never prints keys.
Only the three named collaboration tools can pass a test approval request.
"""
from pathlib import Path
import json
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config, atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve


def main():
    project = Path(__file__).resolve().parents[1]
    root = project / ".test-data" / ("deepseek-model-" + uuid.uuid4().hex[:8])
    c = Coordinator(Config(root))
    server, _ = serve(c)
    report = dict(home=str(root), ok=False, turns=[], approvals=[])
    marker = "DSH_MEMORY_" + uuid.uuid4().hex[:8]
    try:
        g = c.groups.create(dict(name="Harness 模型与恢复验收", members=["deepseek"], workspace=str(root)))
        def turn(text):
            m = c.admin_call("message.send", dict(group_id=g["id"], text=text))
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                for request in c.repo.list("request", g["id"]):
                    if request["status"] != "pending":
                        continue
                    tool = request.get("tool", "")
                    allowed = any(tool.endswith(name) for name in ("teams_inbox_read", "teams_context_get", "teams_reply"))
                    report["approvals"].append(dict(tool=tool, allowed=allowed))
                    c.admin_call("attention.answer", dict(id=request["id"], allow=allowed))
                runs = [r for r in c.repo.list("run", g["id"]) if r["message_id"] == m["id"]]
                if runs and runs[-1]["status"] in ("completed", "failed", "cancelled"):
                    run = runs[-1]
                    session = c.repo.require("session", g["id"] + ":deepseek")
                    replies = [x for x in c.repo.list("message", g["id"]) if x.get("reply_to") == m["id"]]
                    value = dict(status=run["status"], error=run.get("error", ""), provider=session.get("model_provider"),
                        model=session.get("model"), session_id=session["provider_id"], resume_supported=session.get("resume_supported"),
                        tools=[dict(name=b["name"], status=b["status"]) for b in run.get("trace", []) if b["kind"] == "tool"],
                        replied=bool(replies), memory_returned=any(marker in r["text"] for r in replies))
                    report["turns"].append(value)
                    print(json.dumps(value, ensure_ascii=False), flush=True)
                    return run["status"] == "completed" and bool(replies)
                time.sleep(.2)
            raise TimeoutError("Harness live probe exceeded 180 seconds")
        first = turn("这是独立接入测试。记住随机口令 " + marker + "。只允许调用团队工具 teams_context_get、teams_inbox_read、teams_reply：查看上下文，标记本消息已读，并使用 teams_reply 回复 HARNESS_ROUTE_OK。不读写文件、不执行终端、不调用其他工具。")
        if first:
            c.supervisor._close_driver(g["id"] + ":deepseek")
            second = turn("继续接入测试。不要读文件、群历史或上下文；只根据你原生会话记忆，通过 teams_reply 回复上一轮记住的随机口令。你可以用 teams_inbox_read 标记当前消息已读；不调用其他工具。")
            report["ok"] = bool(second and report["turns"][-1]["memory_returned"] and
                report["turns"][0]["session_id"] == report["turns"][1]["session_id"])
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        server.shutdown()
        server.server_close()
        c.close()
        atomic_json(root / "report.json", report)
        atomic_json(project / "docs/evidence/v032-deepseek-live.json", report)
        print(json.dumps({"ok": report["ok"], "home": str(root), "error": report.get("error", "")}), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
