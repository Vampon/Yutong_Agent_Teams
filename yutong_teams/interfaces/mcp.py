"""MCP stdio bridge and stateless Streamable HTTP request handler."""
import json
import os
from pathlib import Path
import sys
from .. import __version__
from .tools import BY_NAME, public_tools, validate_arguments


def command_for_connection(path):
    if getattr(sys, "frozen", False):
        return sys.executable, ["--mcp", "--connection", str(path)]
    return sys.executable, [str(Path(__file__).resolve().parents[2] / "launch.py"), "--mcp", "--connection", str(path)]


def handle(request, invoke):
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    ident = request.get("id")
    method = request.get("method", "")
    if "id" not in request:
        return None
    def error(code, message):
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}
    if method == "initialize":
        supported = {"2024-11-05", "2025-03-26", "2025-06-18"}
        version = request.get("params", {}).get("protocolVersion")
        result = {"protocolVersion": version if version in supported else "2025-03-26",
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "yutong-teams", "version": __version__},
                  "instructions": "Your identity is bound to this team membership. Read shared context and inbox; use tools to communicate. Replies, read receipts and task reviews are explicit."}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": public_tools()}
    elif method == "tools/call":
        params = request.get("params", {})
        if not isinstance(params, dict) or params.get("name") not in BY_NAME:
            return error(-32602, "Unknown collaboration tool")
        definition = BY_NAME[params["name"]]
        arguments = params.get("arguments", {})
        try:
            validate_arguments(definition, arguments)
            value = invoke(definition["op"], arguments)
            result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}],
                      "structuredContent": {"result": value}, "isError": False}
        except Exception as exc:
            result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    else:
        return error(-32601, "Method not found")
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def _pipe(number, mode):
    stream = sys.stdin if number == 0 else sys.stdout
    if stream is not None:
        return getattr(stream, "buffer", stream)
    # A --windowed EXE has no Python stdio wrappers, but MCP's inherited pipe
    # handles still exist. Bind those handles explicitly; never allocate a console.
    if os.name == "nt":
        import ctypes
        import msvcrt
        kernel = ctypes.windll.kernel32
        kernel.GetStdHandle.restype = ctypes.c_void_p
        handle_value = kernel.GetStdHandle(-10 if number == 0 else -11)
        if not handle_value or handle_value == ctypes.c_void_p(-1).value:
            raise RuntimeError("MCP requires redirected stdin/stdout")
        descriptor = msvcrt.open_osfhandle(handle_value, os.O_RDONLY if number == 0 else os.O_WRONLY)
        return os.fdopen(descriptor, mode, buffering=0)
    return os.fdopen(number, mode, buffering=0, closefd=False)


def stdio(connection):
    from ..sdk import AgentClient
    client = AgentClient(connection=connection)
    source, output = _pipe(0, "rb"), _pipe(1, "wb")
    while True:
        raw = source.readline(1_000_001)
        if not raw:
            break
        if len(raw) > 1_000_000:
            return 1
        try:
            reply = handle(json.loads(raw.decode("utf-8")), lambda op, data: client.call(op, **data))
        except (ValueError, UnicodeError):
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if reply is not None:
            output.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
            output.flush()
    return 0
