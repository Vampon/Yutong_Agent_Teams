"""Real Claude public progress, bounded to read-only collaboration tools."""
from pathlib import Path
import json
import sys
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config, atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.interfaces.http import serve

root = Path(__file__).resolve().parents[1] / ".test-data" / ("progress-live-" + uuid.uuid4().hex[:8])
c = Coordinator(Config(root))
server, _ = serve(c)
report = dict(home=str(root), ok=False, observed_live=False)
try:
    c.admin_call("permissions.configure", {"mode": "deny"})
    g = c.groups.create(dict(name="公开过程验收", members=["claude"], workspace=str(root)))
    m = c.admin_call("message.send", dict(group_id=g["id"], text="先在当前输出中用一句话公开说明准备核对协作上下文，再调用 teams_context_get 和 teams_inbox_read。最后使用 teams_reply 回复 LIVE_PROGRESS_OK。不读写文件，不调用终端或其他工具。"))
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        runs = c.snapshot()["runs"]
        if runs:
            run = runs[0]
            if run["status"] in ("running", "waiting") and run["trace"]:
                report["observed_live"] = True
            if run["status"] in ("completed", "failed", "cancelled"):
                detail = c.admin_call("run.get", {"id": run["id"]})
                report.update(status=run["status"], error=run.get("error"),
                    blocks=[{k: b.get(k) for k in ("kind", "name", "status", "call_id")} for b in detail["trace"]],
                    public_text=any(b["kind"] == "text" for b in detail["trace"]),
                    tool_results=any(b["kind"] == "tool" and b.get("status") == "completed" for b in detail["trace"]))
                report["ok"] = run["status"] == "completed" and report["observed_live"] and report["public_text"] and report["tool_results"]
                break
        time.sleep(.2)
    else:
        report["error"] = "Timed out"
finally:
    server.shutdown()
    server.server_close()
    c.close()
    atomic_json(root / "report.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
sys.exit(0 if report["ok"] else 1)
