"""Agent Client Protocol session/new, load, prompt, updates and permissions."""
import json
import time
from ... import __version__
from ..processes import ProcessChannel, executable


class ACPAdapter:
    def __init__(self, config, agent, session, binding, persist):
        self.config, self.agent, self.session = config, agent, session
        self.binding, self.persist = binding, persist
        self.channel, self.sequence = None, 0
        self.tool_calls = {}
        self.model_plan = None

    def _request(self, method, params):
        self.sequence += 1
        self.channel.send({"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": params})
        return self.sequence

    def _wait(self, ident, stop, deadline, emit, approve):
        while True:
            frame = self.channel.next(stop, deadline)
            if frame.get("id") == ident and "method" not in frame:
                if "error" in frame:
                    raise RuntimeError(str(frame["error"].get("message", frame["error"])))
                return frame.get("result", {})
            method = frame.get("method")
            params = frame.get("params", {})
            if method == "session/update":
                update = params.get("update", {})
                kind = update.get("sessionUpdate")
                if kind == "agent_message_chunk":
                    emit("accepted", {})
                    content = update.get("content", {})
                    if content.get("type") == "text":
                        emit("text", {"text": content.get("text", "")})
                elif kind in ("tool_call", "tool_call_update"):
                    emit("accepted", {})
                    data = {"id": update.get("toolCallId"), "status": update.get("status")}
                    if update.get("title") or update.get("name"):
                        data["name"] = update.get("title") or update["name"]
                    if update.get("rawInput") is not None:
                        data["arguments"] = update["rawInput"]
                    if update.get("rawOutput") is not None:
                        data["result"] = update["rawOutput"]
                    elif update.get("content"):
                        data["result"] = "\n".join(str(x.get("content", {}).get("text", "")) for x in update["content"] if x.get("type") == "content" and x.get("content", {}).get("type") == "text")
                    previous = self.tool_calls.setdefault(data.get("id"), {})
                    previous.update({k: v for k, v in data.items() if v is not None})
                    emit("tool", data)
            elif method == "session/request_permission":
                call = params.get("toolCall", {})
                previous = self.tool_calls.get(call.get("toolCallId"), {})
                allowed = approve(call.get("title") or previous.get("name") or "ACP 工具", call.get("rawInput", previous.get("arguments", {})))
                options = params.get("options", [])
                preference = ("allow_once", "allow_always") if allowed else ("reject_once", "reject_always")
                chosen = next((o for k in preference for o in options if o.get("kind") == k), None)
                outcome = {"outcome": "selected", "optionId": chosen["optionId"]} if chosen else {"outcome": "cancelled"}
                self.channel.send({"jsonrpc": "2.0", "id": frame["id"], "result": {"outcome": outcome}})
            elif "id" in frame and method:
                self.channel.send({"jsonrpc": "2.0", "id": frame["id"], "error": {"code": -32601, "message": "Client capability not supported"}})

    def _start(self, stop, emit, approve):
        command = executable(self.agent.get("command"), self.agent["kind"])
        if self.agent["kind"] == "deepseek":
            from .deepseek_config import resolve, launch_patch
            self.model_plan = resolve(self.agent)
            command += ["--profile", "acp"] + launch_patch(self.model_plan, self.binding["directory"])
        command += self.agent.get("args", [])
        env = {}
        if self.agent["kind"] == "deepseek" and self.config.secret(self.agent):
            env["DEEPSEEK_API_KEY"] = self.config.secret(self.agent)
        self.channel = ProcessChannel(command, self.binding["workspace"], env)
        deadline = time.monotonic() + 60
        # session/load may replay history. Those frames are not output or delivery
        # evidence for the new prompt we have not sent yet.
        replay = lambda *args: None
        caps = self._wait(self._request("initialize", {"protocolVersion": 1, "clientCapabilities": {},
                          "clientInfo": {"name": "yutong-teams", "version": __version__}}), stop, deadline, replay, approve)
        definition = self.binding["connection"]["mcp_config"]["mcpServers"]["teams"]
        server = dict(name="teams", command=definition["command"], args=definition["args"], env=[])
        params = dict(cwd=self.binding["workspace"], mcpServers=[server])
        saved = self.session.get("provider_id")
        capabilities = caps.get("agentCapabilities", {})
        sessions = capabilities.get("sessionCapabilities", {})
        resume_method = "session/resume" if "resume" in sessions else "session/load" if capabilities.get("loadSession") else ""
        if saved:
            if not resume_method:
                raise RuntimeError("该 ACP 运行器不支持恢复已保存会话，请明确选择新建会话")
            params["sessionId"] = saved
        response = self._wait(self._request(resume_method if saved else "session/new", params), stop, deadline, replay, approve)
        sid = response.get("sessionId", saved)
        if not sid:
            raise RuntimeError("ACP 未返回会话 ID")
        self.session["provider_id"] = sid
        self.persist(provider_id=sid, resume_supported=bool(resume_method))
        self._select_model(response, saved, stop, deadline, replay, approve)

    def _select_model(self, response, saved, stop, deadline, emit, approve):
        if not self.model_plan:
            return
        plan = self.model_plan
        option = next((o for o in response.get("configOptions", []) if o.get("category") == "model" or o.get("id") == "model"), None)
        if not option:
            return
        current = option.get("currentValue")
        # Established sessions retain their selected model. Failed first turns
        # may adopt the corrected settings instead of remaining on the bad route.
        if plan["provider"] and (not saved or not self.session.get("turns", 0)):
            wanted = [plan["provider"], plan["model"]]
            def choices(items):
                for item in items:
                    if "options" in item:
                        yield from choices(item["options"])
                    else:
                        yield item.get("value")
            values = list(choices(option.get("options", [])))
            def route(value):
                try:
                    return json.loads(value)
                except (TypeError, ValueError):
                    return None
            selected = next((value for value in values if route(value) == wanted), None)
            if selected is None:
                raise RuntimeError("Harness 未提供所选模型：%s / %s，请检查模型配置来源" % tuple(wanted))
            if route(current) != wanted:
                result = self._wait(self._request("session/set_config_option", {
                    "sessionId": self.session["provider_id"], "configId": option["id"], "value": selected,
                }), stop, deadline, emit, approve)
                option = next((o for o in result.get("configOptions", []) if o.get("id") == option["id"]), {})
                current = option.get("currentValue")
                if route(current) != wanted:
                    raise RuntimeError("Harness 未确认模型切换，未发送任务")
        try:
            provider, model = json.loads(current)
        except (TypeError, ValueError):
            return
        self.persist(model_provider=provider, model=model, model_source=plan["source"])

    def run(self, prompt, turn, stop, emit, approve):
        self.tool_calls.clear()
        parts = []
        def event(kind, data):
            if kind == "text":
                parts.append(data.get("text", ""))
            emit(kind, data)
        if self.channel is None or self.channel.proc.poll() is not None:
            self._start(stop, event, approve)
        ident = self._request("session/prompt", {"sessionId": self.session["provider_id"], "prompt": [{"type": "text", "text": prompt}]})
        response = self._wait(ident, stop, time.monotonic() + int(self.agent.get("timeout") or 600), event, approve)
        emit("accepted", {})
        if response.get("stopReason") not in ("end_turn", None):
            raise RuntimeError("ACP 回合终止：" + str(response.get("stopReason")))
        self.session["turns"] = self.session.get("turns", 0) + 1
        return "".join(parts)

    def close(self):
        if self.channel:
            self.channel.close()
            self.channel = None
