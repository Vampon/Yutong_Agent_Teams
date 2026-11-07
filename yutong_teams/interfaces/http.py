"""Loopback desktop API plus identity-scoped agent HTTP and MCP endpoints."""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
from pathlib import Path
import secrets
from socketserver import TCPServer
import threading
from urllib.parse import urlparse
from ..config import asset
from ..core.contracts import Forbidden, Conflict
from .mcp import handle as mcp_handle


class TeamsHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        """Bind without reverse DNS, which can return non-UTF-8 Windows names.

        HTTPServer resolves the bound address only to fill server_name. Our
        handlers use the bound endpoint, so the numeric address is sufficient.
        This also avoids a DNS dependency for starting the desktop or gateway.
        """
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def serve(control, host="127.0.0.1", port=0, token=None, worker=False):
    admin_token = token or secrets.token_urlsafe(40)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, value=None, content_type="application/json; charset=utf-8"):
            raw = b"" if value is None else value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def origin_allowed(self):
            origin = self.headers.get("Origin")
            return not origin or origin == "http://" + self.headers.get("Host", "")

        def is_local(self):
            return self.client_address[0] in ("127.0.0.1", "::1")

        def principal(self):
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                raise Forbidden("缺少成员凭据")
            return control.access.authenticate(auth[7:])

        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/mcp":
                try:
                    if not self.origin_allowed():
                        raise Forbidden("Origin rejected")
                    self.principal()
                    self.respond(405, {"error": "Server-initiated SSE is not offered; use POST"})
                except Forbidden as exc:
                    self.respond(403, {"error": str(exc)})
                return
            if worker or not self.is_local():
                self.respond(404, {"error": "Not found"})
                return
            root = asset("web").resolve()
            name = "index.html" if route == "/" else route.lstrip("/")
            file = (root / name).resolve()
            if root not in file.parents or file.suffix not in (".html", ".js", ".css", ".svg", ".png") or not file.is_file():
                self.respond(404, {"error": "Not found"})
                return
            content_type = "image/png" if file.suffix == ".png" else (mimetypes.guess_type(str(file))[0] or "text/plain") + "; charset=utf-8"
            self.respond(200, file.read_bytes(), content_type)

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_000_000:
                    raise ValueError("请求大小无效")
                self.connection.settimeout(15)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("请求体不完整")
            except Exception:
                self.respond(400, {"ok": False, "error": "请求大小无效"})
                return
            if not self.origin_allowed():
                self.respond(403, {"ok": False, "error": "Origin rejected"})
                return
            try:
                data = json.loads(raw)
                route = urlparse(self.path).path
                if route == "/api" and not worker:
                    if not self.is_local() or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + admin_token):
                        self.respond(401, {"ok": False, "error": "桌面访问凭据无效"})
                        return
                    if not isinstance(data, dict):
                        raise ValueError("请求应为对象")
                    op, args = data["op"], data.get("data", {})
                    if op == "home.open":
                        import os
                        os.startfile(str(control.config.root)); value = True
                    elif op == "sdk.export":
                        import os
                        import shutil
                        target = control.config.root / "integrations" / "teams_client.py"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(str(asset("sdk.py")), str(target))
                        os.startfile(str(target.parent))
                        value = str(target)
                    elif op == "folder.pick":
                        import webview
                        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
                        value = result[0] if result else ""
                    else:
                        value = control.admin_call(op, args)
                    self.respond(200, {"ok": True, "data": value})
                elif route in ("/agent/v1", "/mcp"):
                    p = self.principal()
                    if route == "/mcp":
                        value = mcp_handle(data, lambda op, args: control.agent_call(p, op, args))
                        self.respond(202 if value is None else 200, value)
                    else:
                        if not isinstance(data, dict):
                            raise ValueError("请求应为对象")
                        value = control.agent_call(p, data["op"], data.get("data", {}))
                        self.respond(200, {"ok": True, "data": value})
                else:
                    self.respond(404, {"ok": False, "error": "Unknown endpoint"})
            except Exception as exc:
                status = 403 if isinstance(exc, Forbidden) else 409 if isinstance(exc, Conflict) else 400
                self.respond(status, {"ok": False, "error": control.config.redact(str(exc)), "code": getattr(exc, "code", "invalid_request")})
    server = TeamsHTTPServer((host, port), Handler)
    logging.info("%s HTTP listening on %s:%d (reverse DNS disabled)", "Agent" if worker else "Desktop", host, server.server_port)
    server.daemon_threads = True
    if not worker or not control.endpoint:
        control.bind("http://127.0.0.1:%d" % server.server_port)
    threading.Thread(target=server.serve_forever, daemon=True, name="teams-http").start()
    return server, admin_token
