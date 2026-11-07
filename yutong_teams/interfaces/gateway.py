"""Optional LAN agent gateway; desktop admin operations are never served here."""
import threading
from urllib.parse import urlparse
from ..config import atomic_json


class Gateway:
    def __init__(self, control):
        self.control, self.server = control, None
        self.lock = threading.RLock()

    def configure(self, values, save=True):
        from .http import serve
        with self.lock:
            enabled = bool(values.get("enabled"))
            host = str(values.get("host") or "0.0.0.0")
            port = int(values.get("port") or 43821)
            public_url = str(values.get("public_url") or "").rstrip("/")
            parsed = urlparse(public_url)
            if enabled and (not 1024 <= port <= 65535 or parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path or parsed.username or parsed.query or parsed.fragment):
                raise ValueError("填写可从其他电脑访问的 HTTP(S) 根地址，以及 1024–65535 的监听端口")
            previous = self.control.config.data.get("gateway", {})
            unchanged = self.server and previous.get("host") == host and previous.get("port") == port
            replacement = None
            if enabled and not unchanged:
                replacement, _ = serve(self.control, host, port, worker=True)
            if self.server and (not enabled or replacement):
                self.server.shutdown()
                self.server.server_close()
                self.server = None
            if replacement:
                self.server = replacement
            config = dict(enabled=enabled, host=host, port=port, public_url=public_url)
            if save:
                with self.control.config.lock:
                    self.control.config.data["gateway"] = config
                    atomic_json(self.control.config.path, self.control.config.data)
                with self.control.repo.transaction():
                    self.control.repo.emit("", "gateway.configured", "human", {"enabled": enabled})
            return config

    def close(self):
        with self.lock:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
                self.server = None
