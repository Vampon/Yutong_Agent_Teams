"""Bounded, provider-neutral public output for live UI and historical runs.

Only explicit text/tool/progress events enter this projection. Hidden reasoning
channels are never treated as public output. Collaboration messages stay separate.
"""
import copy
import json
from ..core.contracts import now

MAX_BLOCKS = 80
MAX_CHARS = 64000


def text_value(value):
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def apply(run, kind, data, stamp=None):
    stamp = stamp or now()
    blocks = run.setdefault("trace", [])
    if data.get("truncated"):
        run["trace_truncated"] = True
    run["trace_version"] = run.get("trace_version", 0) + 1

    def add(type, **fields):
        block = dict(id=str(run["trace_version"]), kind=type, time=stamp, **fields)
        blocks.append(block)
        return block

    if kind in ("text", "text_delta", "text.replace"):
        text = str(data.get("text", ""))
        if not text:
            return
        if kind == "text.replace":
            stream = data.get("stream", "replace")
            block = next((b for b in reversed(blocks) if b.get("stream") == stream), None)
            if block is None:
                block = add("text", text="", stream=stream)
            block["text"] = text[-16000:]
            if len(text) > 16000:
                run["trace_truncated"] = True
        else:
            block = blocks[-1] if blocks and blocks[-1]["kind"] == "text" else add("text", text="")
            block["text"] = (block["text"] + text)[-16000:]
            if len(block["text"]) == 16000:
                run["trace_truncated"] = True
    elif kind in ("tool", "tool_call", "tool_result", "tool.permission"):
        ident = data.get("id") or data.get("tool_call_id") or data.get("tool_use_id")
        name = data.get("name") or data.get("tool") or ""
        block = next((b for b in reversed(blocks) if b["kind"] == "tool" and
                      ((ident and b.get("call_id") == ident) or
                       (not ident and b.get("name") == name and b.get("status") in ("running", "pending", "awaiting_approval")))), None)
        if block is None:
            block = add("tool", call_id=ident or "", name=name or "工具调用", status="running")
        if name:
            block["name"] = str(name)[:200]
        if "arguments" in data or "args" in data:
            arguments = text_value(data.get("arguments", data.get("args")))
            block["arguments"] = arguments[:6000]
            if len(arguments) > 6000:
                run["trace_truncated"] = True
        result = data.get("result", data.get("output"))
        if result is not None:
            output = text_value(result)
            block["result"] = output[:8000]
            if len(output) > 8000:
                run["trace_truncated"] = True
        status = data.get("status")
        if kind == "tool_result":
            status = "failed" if data.get("is_error") else "completed"
        if kind == "tool.permission":
            status = "running" if data.get("allow") else "denied"
            block["permission"] = data.get("policy", "human")
        if status:
            block["status"] = {"in_progress": "running"}.get(status, status)
        block["updated"] = stamp
    elif kind == "status":
        text = str(data.get("text", ""))
        if not text:
            return
        if blocks and blocks[-1]["kind"] == "status" and blocks[-1]["text"] == text:
            return
        add("status", text=text[:1000])
    else:
        return
    run["last_output_at"] = stamp
    while len(blocks) > MAX_BLOCKS or (len(blocks) > 1 and len(json.dumps(blocks, ensure_ascii=False)) > MAX_CHARS):
        blocks.pop(0)
        run["trace_truncated"] = True


def projected(run, compact=False):
    value = copy.deepcopy(run)
    if "trace" not in value:
        for event in value.get("events", []):
            apply(value, event["type"], event.get("data", {}), event.get("time"))
        if not any(b["kind"] == "text" for b in value.get("trace", [])) and value.get("preview"):
            apply(value, "text", {"text": value["preview"]}, value.get("finished") or value.get("created"))
    value.setdefault("trace", [])
    if compact:
        value["trace_count"] = len(value["trace"])
        value["trace"] = value["trace"][-6:]
        for block in value["trace"]:
            for key in ("text", "arguments", "result"):
                if key in block:
                    block[key] = block[key][-1800:]
        value["preview"] = value.get("preview", "")[-2000:]
    return value
