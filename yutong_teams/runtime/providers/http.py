"""Text-response HTTP adapters. These do not claim native collaboration tools."""
import json, queue, threading, time, uuid
import httpx
from ..processes import Cancelled

class HttpAdapter:
    def __init__(self, config, agent, session, binding, persist):
        self.config,self.agent,self.session,self.binding,self.persist=config,agent,session,binding,persist
    def run(self, prompt, turn, stop, emit, approve):
        value=self.http(self.agent,prompt,dict(turn,group_id=turn["group_id"]+":"+self.session["generation"]),stop,emit)
        emit("accepted",{})
        return value
    def close(self):
        pass

    def http(self, a, prompt, job, stop, emit):
        secret = self.config.secret(a)
        headers = {}
        if a["kind"] == "adp":
            body = {"AppKey": secret, "UserId": a["user_id"], "VisitorId": a["user_id"],
                    "RequestId": uuid.uuid4().hex, "ConversationId": uuid.uuid5(uuid.NAMESPACE_URL, job["group_id"] + ":" + a["id"] + ":" + a["user_id"]).hex,
                    "Contents": [{"Type": "text", "Text": prompt}], "Incremental": True, "Stream": "enable"}
            if a.get("source_id"):
                if a.get("allow_personas") is not True:
                    raise ValueError("当前 ADP 接入未启用角色覆盖")
                body["SystemRole"] = "\n".join(x for x in (a.get("role"), a.get("instructions")) if x)
        else:
            body = {"message": prompt, "session_id": job["group_id"] + ":" + a["id"], "request_id": job["id"]}
            if secret:
                headers["Authorization"] = "Bearer " + secret
        result_queue = queue.Queue()
        # Isolate blocking socket IO: cancellation closes the stream and never retries POST.
        client = httpx.Client(verify=a.get("ca_bundle") or True, trust_env=bool(a.get("use_proxy")), timeout=int(a.get("timeout") or 600))
        def request():
            try:
                with client.stream("POST", a["url"], json=body, headers=headers) as response:
                    response.raise_for_status()
                    if a["kind"] != "adp":
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 4_000_000:
                                raise ValueError("HTTP 回复超过 4 MB")
                        value = json.loads(raw)
                        for key in (a.get("response_path") or "result").split("."):
                            value = value[key]
                        result_queue.put((True, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)))
                        return
                    parts, types, size, complete = {}, {}, 0, False
                    for frame in sse_frames(response.iter_lines()):
                        size += len(json.dumps(frame))
                        if size > 4_000_000:
                            raise ValueError("ADP 回复超过 4 MB")
                        if stop.is_set():
                            raise Cancelled()
                        typ = frame.get("Type")
                        if typ == "error" or frame.get("Error"):
                            raise RuntimeError("ADP 错误：" + str(frame.get("Error")))
                        if typ in ("message.added", "message.done"):
                            msg = frame.get("Message", {})
                            types[frame.get("MessageId") or msg.get("MessageId")] = msg.get("Type")
                        if typ in ("text.delta", "text.replace"):
                            key = (frame.get("MessageId"), frame.get("ContentIndex", 0))
                            text = frame.get("Text", "")
                            parts[key] = parts.get(key, "") + text if typ == "text.delta" else text
                            if types.get(key[0]) == "reply":
                                emit("text.replace", {"text": "\n".join(v for (mid, _), v in parts.items() if types.get(mid) == "reply")})
                        if typ == "response.completed":
                            record = frame.get("Response", {})
                            if record.get("Status") != "success":
                                raise RuntimeError("ADP 未成功：" + str(record.get("StatusDesc") or record.get("Status")))
                            text = "\n".join(c.get("Text", "") for m in record.get("Messages", []) if m.get("Type") == "reply" for c in m.get("Contents", []) if c.get("Type") == "text")
                            result_queue.put((True, text or "\n".join(v for (mid, _), v in parts.items() if types.get(mid) == "reply")))
                            complete = True
                            break
                    if not complete:
                        raise RuntimeError("ADP 流提前结束，缺少成功完成事件")
            except Exception as exc:
                result_queue.put((False, exc))
        threading.Thread(target=request, daemon=True).start()
        deadline = time.monotonic() + int(a.get("timeout") or 600)
        try:
            while True:
                if stop.is_set():
                    raise Cancelled("已停止等待；远端已开始的业务动作可能仍在执行")
                if time.monotonic() > deadline:
                    raise TimeoutError("接口超时；远端是否继续执行需在原平台核对")
                try:
                    ok, value = result_queue.get(timeout=.1)
                except queue.Empty:
                    continue
                if not ok:
                    raise value
                if not value.strip():
                    raise RuntimeError("接口未返回有效正文")
                return value
        finally:
            client.close()

def sse_frames(lines):
    pending = []
    for line in lines:
        if not line:
            if pending:
                yield json.loads("\n".join(pending))
                pending = []
        elif line.startswith("data:"):
            pending.append(line[5:].lstrip())
    if pending:
        yield json.loads("\n".join(pending))
