import time
from ...config import asset
from ...interfaces.tools import TOOLS
from ..processes import ProcessChannel, executable


class CCUAdapter:
    def __init__(self, config, agent, session, binding, persist):
        self.config, self.agent, self.session = config, agent, session
        self.binding, self.persist = binding, persist
        self.channel = None

    def _start(self, stop):
        command = executable(self.agent.get("command"), "ccu") + [str(asset("bridges/ccu.py"))] + self.agent.get("args", [])
        self.channel = ProcessChannel(command, self.binding["workspace"], {"CCU_AGENT_WORKSPACE": self.binding["workspace"]})
        connection = self.binding["connection"]
        self.channel.send(dict(project=self.agent["project"], config=self.agent.get("config_path", ""),
            session_id=self.session.get("provider_id", ""), tools=TOOLS, endpoint=self.binding["endpoint"], token=connection["token"]))
        deadline = time.monotonic() + 60
        while True:
            frame = self.channel.next(stop, deadline)
            if frame["type"] == "ready":
                self.session["provider_id"] = frame["session_id"]
                self.persist(provider_id=frame["session_id"])
                return
            if frame["type"] in ("fatal", "error"):
                raise RuntimeError(frame.get("message", "CCU 初始化失败"))

    def run(self, prompt, turn, stop, emit, approve):
        if self.channel is None or self.channel.proc.poll() is not None:
            self._start(stop)
        self.channel.send({"type": "prompt", "prompt": prompt})
        deadline = time.monotonic() + int(self.agent.get("timeout") or 600)
        while True:
            frame = self.channel.next(stop, deadline)
            kind = frame["type"]
            if kind == "approval":
                self.channel.send({"approved": approve(frame.get("name", "tool"), frame.get("arguments", {}))})
            elif kind in ("fatal", "error"):
                raise RuntimeError(frame.get("message", "CCU 未完成"))
            elif kind == "final":
                return frame.get("text", "")
            else:
                emit("text" if kind == "text_delta" else kind, frame)

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None
