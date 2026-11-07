"""Claude's bidirectional stream protocol; one live process per membership."""
import time
import uuid
from ...config import atomic_json
from ..processes import ProcessChannel, executable


class ClaudeAdapter:
    def __init__(self, config, agent, session, binding, persist):
        self.config, self.agent, self.session = config, agent, session
        self.binding, self.persist = binding, persist
        self.channel = None

    def _start(self, stop):
        path = self.binding["directory"] / "mcp.json"
        atomic_json(path, self.binding["connection"]["mcp_config"])
        command = executable(self.agent.get("command"), "claude")
        command += ["-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
                    "--include-partial-messages", "--mcp-config", str(path),
                    "--permission-prompt-tool", "stdio", "--allowedTools", "mcp__teams__*"]
        # The workbench resolves surfaced requests centrally, including live policy
        # changes. Do not switch the native runner into a bypass mode.
        command += ["--permission-mode", "default"]
        saved = self.session.get("provider_id")
        command += ["--resume", saved] if saved else ["--session-id", str(uuid.uuid4())]
        command += self.agent.get("args", [])
        self.channel = ProcessChannel(command, self.binding["workspace"])
        request_id = uuid.uuid4().hex
        self.channel.send({"type": "control_request", "request_id": request_id,
                           "request": {"subtype": "initialize"}})
        deadline = time.monotonic() + 60
        while True:
            frame = self.channel.next(stop, deadline)
            if frame.get("type") == "control_response":
                response = frame.get("response", {})
                if response.get("request_id") == request_id:
                    if response.get("subtype") == "error":
                        raise RuntimeError(str(response.get("error")))
                    break

    def run(self, prompt, turn, stop, emit, approve):
        if self.channel is None or self.channel.proc.poll() is not None:
            self._start(stop)
        self.channel.send({"type": "user", "message": {"role": "user", "content": prompt},
                           "parent_tool_use_id": None, "session_id": self.session.get("provider_id", "")})
        deadline = time.monotonic() + int(self.agent.get("timeout") or 600)
        while True:
            frame = self.channel.next(stop, deadline)
            if frame.get("session_id") and frame["session_id"] != self.session.get("provider_id"):
                sid = frame["session_id"]
                self.session["provider_id"] = sid
                self.persist(provider_id=sid)
            kind = frame.get("type")
            if kind == "control_request":
                request = frame.get("request", {})
                if request.get("subtype") == "can_use_tool":
                    name, arguments = request.get("tool_name", "tool"), request.get("input", {})
                    allowed = name.startswith("mcp__teams__teams_") or approve(name, arguments)
                    decision = {"behavior": "allow", "updatedInput": arguments} if allowed else {"behavior": "deny", "message": "Execution denied by the workbench's user or tool approval policy"}
                    self.channel.send({"type": "control_response", "response": {"subtype": "success", "request_id": frame["request_id"], "response": decision}})
                else:
                    self.channel.send({"type": "control_response", "response": {"subtype": "error", "request_id": frame["request_id"], "error": "Unsupported control request"}})
            elif kind == "assistant":
                emit("accepted", {})
                for block in frame.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use":
                        emit("tool", {"id": block.get("id"), "name": block.get("name"), "arguments": block.get("input"), "status": "running"})
            elif kind == "user":
                for block in frame.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        content = block.get("content", "")
                        if isinstance(content, list):
                            content = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict) and item.get("type") == "text")
                        emit("tool_result", {"id": block.get("tool_use_id"), "result": content, "is_error": block.get("is_error", False)})
            elif kind == "stream_event":
                event = frame.get("event", {})
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    emit("accepted", {})
                    emit("text", {"text": delta.get("text", "")})
            elif kind == "result":
                if frame.get("is_error"):
                    raise RuntimeError(frame.get("result") or str(frame.get("errors")) or "Claude 未成功完成")
                emit("accepted", {})
                return frame.get("result", "")

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None
