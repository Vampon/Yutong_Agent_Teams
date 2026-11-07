import json
import time
from ...config import asset, atomic_json
from ...interfaces.tools import TOOLS, BY_NAME, validate_arguments
from ..processes import ProcessChannel, executable, Cancelled


class MatlabAdapter:
    def __init__(self, config, agent, session, binding, persist):
        self.config, self.agent, self.session = config, agent, session
        self.binding, self.persist = binding, persist
        self.channel = None

    def _read(self, path):
        return json.loads(path.read_text("utf-8-sig"))

    def _check(self, stop, deadline, folder):
        if stop.is_set():
            self.close()
            raise Cancelled("MATLAB 执行已停止")
        for base in (folder, self.binding["directory"]):
            if (base / "fatal.json").exists():
                raise RuntimeError(self._read(base / "fatal.json")["error"])
        if self.channel.proc.poll() is not None:
            raise RuntimeError("MATLAB 已退出，请检查会话日志")
        if time.monotonic() > deadline:
            self.close()
            raise TimeoutError("MATLAB 会话超时；没有自动重放工具操作")

    def _start(self, stop, deadline):
        folder = self.binding["directory"]
        for name in ("ready.json", "fatal.json", "inbox.json", "close.json"):
            path = folder / name
            if path.exists():
                path.unlink()
        atomic_json(folder / "init.json", dict(project=self.agent["project"], workspace=self.binding["workspace"], tools=TOOLS))
        quote = lambda path: str(path).replace("'", "''")
        expression = "addpath('%s'); yat_run('%s');" % (quote(asset("bridges")), quote(folder))
        command = executable(self.agent.get("command"), "matlab") + ["-nodesktop", "-nosplash", "-batch", expression,
                    "-logfile", str(folder / "matlab.log")] + self.agent.get("args", [])
        self.channel = ProcessChannel(command, self.binding["workspace"])
        while not (folder / "ready.json").exists():
            self._check(stop, deadline, folder)
            time.sleep(.15)
        self.persist(provider_id=self.session["generation"])

    def run(self, prompt, turn, stop, emit, approve):
        deadline = time.monotonic() + int(self.agent.get("timeout") or 600)
        folder = self.binding["directory"] / turn["id"]
        folder.mkdir(parents=True, exist_ok=True)
        if self.channel is None or self.channel.proc.poll() is not None:
            self._start(stop, deadline)
        atomic_json(self.binding["directory"] / "inbox.json", dict(id=turn["id"], runDir=str(folder), prompt=prompt))
        seen, revision = set(), -1
        progress_seen = set()
        def progress_events():
            for path in sorted(folder.glob("event-*.json")):
                if path.name in progress_seen:
                    continue
                progress = self._read(path)
                self._progress(progress, emit)
                progress_seen.add(path.name)
        while True:
            self._check(stop, deadline, folder)
            if (folder / "accepted.json").exists():
                emit("accepted", {})
            progress_events()
            for path in folder.glob("call-*.json"):
                if path.name in seen:
                    continue
                call = self._read(path)
                if call["kind"] == "collaboration":
                    try:
                        definition = BY_NAME[call["name"]]
                        arguments = call.get("arguments") or {}
                        validate_arguments(definition, arguments)
                        value = self.binding["invoke"](definition["op"], arguments)
                        answer = {"result": json.dumps(value, ensure_ascii=False)}
                    except Exception as exc:
                        answer = {"result": json.dumps({"error": str(exc)}, ensure_ascii=False)}
                else:
                    answer = {"approved": approve(call["name"], call.get("arguments", {}))}
                atomic_json(folder / ("reply-" + call["id"] + ".json"), answer)
                seen.add(path.name)
            if (folder / "progress.json").exists():
                progress = self._read(folder / "progress.json")
                if progress.get("revision") != revision:
                    revision = progress.get("revision")
                    self._progress(progress, emit)
            if (folder / "result.json").exists():
                progress_events()
                result = self._read(folder / "result.json")
                if not result.get("ok"):
                    raise RuntimeError(result.get("error", "MATLAB 未完成"))
                return result.get("response", "")
            time.sleep(.15)

    @staticmethod
    def _progress(progress, emit):
        phase, data = progress.get("phase"), progress.get("data") or {}
        if phase == "progress":
            if data.get("stream"):
                emit("text.replace", {"text": data["stream"], "stream": "matlab-" + str(data.get("generation", 0))})
            label = {"thinking": "等待模型输出", "generating": "正在输出", "tool": "正在执行工具"}.get(data.get("phase"))
            if label:
                emit("status", {"text": label})
        elif phase == "tool":
            emit("tool", {"id": data.get("id"), "name": data.get("name"), "arguments": data.get("arguments", {}), "status": "running"})
        elif phase == "toolResult":
            req, reply = data.get("request", {}), data.get("reply", {})
            # A remote tool's local approval reply is not its execution result.
            if req.get("remote") and reply.get("approved"):
                return
            emit("tool_result", {"id": req.get("id"), "name": req.get("name"), "result": reply.get("result", ""), "is_error": reply.get("approved") is False})
        elif phase == "storage":
            emit("status", {"text": data.get("error", "正在保存结果")})

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None
