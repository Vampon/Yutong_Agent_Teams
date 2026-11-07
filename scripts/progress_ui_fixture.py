"""Synthetic streaming UI fixture; never calls a model or modifies user projects."""
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from yutong_teams.config import Config, atomic_json
from yutong_teams.control import Coordinator
from yutong_teams.core.contracts import HUMAN, Principal
from yutong_teams.interfaces.http import serve
from yutong_teams.runtime.registry import default_registry


class StreamingFixture:
    def __init__(self, config, agent, session, binding, persist):
        self.agent, self.binding = agent, binding
        persist(provider_id="fixture-" + agent["id"])

    def close(self):
        pass

    def run(self, prompt, turn, stop, emit, approve):
        emit("accepted", {})
        emit("text", {"text": "先核对需求边界，再检查实现与测试证据。\n"})
        emit("tool", {"id": "fixture-read", "name": "read_requirements", "arguments": {"path": "specifications/control.md"}})
        if stop.wait(.3):
            return "stopped"
        emit("tool_result", {"id": "fixture-read", "result": "夹具输出：3 项边界条件已载入。"})
        for i in range(1, 25):
            if stop.wait(.3):
                return "stopped"
            emit("text", {"text": "正在复核第 %d 个检查点。\n" % i})
        allowed = approve("write_review", {"path": "review.md"})
        emit("text", {"text": "\n确认结果：" + ("已允许" if allowed else "已拒绝")})
        self.binding["invoke"]("message.reply", dict(reply_to=turn["message_id"], text="夹具执行完成，已记录检查过程。", mode="mail"))
        return "Fixture final output"


root = Path(__file__).resolve().parents[1] / ".test-data" / ("progress-ui-" + uuid.uuid4().hex[:8])
config = Config(root)
registry = default_registry()
for kind in ("claude", "deepseek"):
    registry.get(kind).factory = StreamingFixture
    registry.get(kind).capabilities["local"] = False
c = Coordinator(config, registry=registry)
server, token = serve(c, port=44992)
g = c.groups.create(dict(name="控制策略联合评审", members=["claude", "deepseek"], goal="明确需求边界，核对控制策略实现与测试证据。"))["id"]
p = Principal(actor_id="claude", group_id=g)
q = Principal(actor_id="deepseek", group_id=g)
for i in range(12):
    c.messages.send(p if i % 2 == 0 else q, g, dict(text="评审记录 %d：已对齐接口、边界条件与验收依据。" % (i + 1), targets=["human"], mode="mail"))
task = c.tasks.create(HUMAN, g, dict(title="评审 quicksort.py 实现", agent_id="deepseek", description="检查分区逻辑、边界条件、复杂度及测试覆盖。"))
c.messages.send(p, g, dict(text="任务分配：评审 quicksort.py 实现\n请交叉检查实现与测试依据。", targets=["deepseek"], mode="mail", task_id=task["id"]), origin="task_assignment")
c.messages.send(p, g, dict(text="实现已提交，已请 DeepSeek 进行交叉评审。", targets=["human"], mode="mail"))
atomic_json(root.parent / "progress-ui-server.json", dict(url="http://127.0.0.1:%d/#" % server.server_port + token, home=str(root), group_id=g))
print("Progress UI fixture ready", flush=True)
try:
    while True:
        time.sleep(.5)
except KeyboardInterrupt:
    pass
finally:
    server.shutdown()
    server.server_close()
    c.close()
