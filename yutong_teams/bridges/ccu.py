"""One native CCU session; collaboration goes through Teams' scoped API."""
import json
import os
import sys
import urllib.request
import urllib.error


def emit(kind, **data):
    print("YAT_EVENT " + json.dumps(dict(type=kind, **data), ensure_ascii=False), flush=True)


def main():
    setup = json.loads(sys.stdin.readline())
    project = os.path.abspath(setup["project"])
    sys.path.insert(0, project)
    from ccu_agent.core.runtime import build_runtime
    from ccu_agent.tools.base import make_tool
    runtime = build_runtime(setup.get("config") or os.path.join(project, "config.yaml"))
    def invoke(op, args):
        payload = json.dumps({"op": op, "data": args}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(setup["endpoint"] + "/agent/v1", data=payload,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + setup["token"]})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=30) as response:
                record = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            record = json.loads(exc.read())
        if not record.get("ok"):
            raise RuntimeError(record.get("error", "协作请求失败"))
        return record["data"]
    try:
        for definition in setup["tools"]:
            def call(op=definition["op"], **arguments):
                return invoke(op, arguments)
            runtime.registry.register(make_tool(definition["name"], definition["description"],
                                                definition["inputSchema"], call, category="team_collaboration"))
        agent = runtime.new_agent(setup.get("session_id") or None)
        # Keep CCU's domain router, while making the collaboration channel
        # available independently of its per-task tool shortlist.
        if agent.capability_router is not None:
            class CollaborationRouter:
                def __init__(self, original):
                    self.original = original
                def __getattr__(self, key):
                    return getattr(self.original, key)
                def route(self, *args, **kwargs):
                    plan = self.original.route(*args, **kwargs)
                    plan.active_tools = list(dict.fromkeys(plan.active_tools + [d["name"] for d in setup["tools"]]))
                    return plan
            agent.capability_router = CollaborationRouter(agent.capability_router)
        agent.auto_approve = False
        emit("ready", session_id=agent.session.id)
        for line in sys.stdin:
            command = json.loads(line)
            if command.get("type") == "close":
                break
            def approval(name, args):
                if name in {d["name"] for d in setup["tools"]}:
                    return True
                emit("approval", name=name, arguments=args)
                return json.loads(sys.stdin.readline()).get("approved") is True
            def events(event):
                kind = event.type.value if hasattr(event.type, "value") else str(event.type)
                if kind in ("text_delta", "tool_call", "tool_result"):
                    emit(kind, **event.data)
            try:
                emit("accepted")
                result = agent.run(command["prompt"], on_event=events, approval_callback=approval)
                emit("final", text=result, session_id=agent.session.id)
            except Exception as exc:
                emit("error", message=str(exc), session_id=agent.session.id)
    finally:
        runtime.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit("fatal", message=str(exc))
        sys.exit(1)
