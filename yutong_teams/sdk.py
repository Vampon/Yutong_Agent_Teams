"""Small synchronous agent client; HTTP use needs only Python's standard library.

Copy this module into another agent system or import it normally. Frameworks
keep their own model, tools and session; this client only adds collaboration.
POSTs are never automatically replayed after an ambiguous connection failure.
"""
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request
import uuid


def _unprotect(value):
    """Read a Windows user-protected profile without importing the desktop app."""
    import base64
    import ctypes
    import os
    if os.name != "nt":
        raise RuntimeError("Windows protected profiles are local to their user; use endpoint/token on another machine")
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value)
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(target.data, target.size).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


class AgentClient:
    @classmethod
    def from_connection(cls, path, **kwargs):
        return cls(connection=path, **kwargs)

    def __init__(self, endpoint="", token="", connection=None, timeout=30, ca_bundle=None):
        self.endpoint, self.token = endpoint.rstrip("/"), token
        self.connection = str(connection) if connection else ""
        self.timeout, self.ca_bundle = timeout, ca_bundle

    def credentials(self):
        if not self.connection:
            return self.endpoint.removesuffix("/agent/v1") if hasattr(str, "removesuffix") else self.endpoint.replace("/agent/v1", ""), self.token
        data = json.loads(Path(self.connection).read_text("utf-8"))
        if "protected_token" in data:
            token = _unprotect(data["protected_token"])
        else:
            token = data["token"]
        return data["endpoint"].rstrip("/").replace("/agent/v1", ""), token

    def call(self, op, **data):
        endpoint, token = self.credentials()
        raw = json.dumps({"op": op, "data": data}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(endpoint + "/agent/v1", data=raw,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        handler = urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=self.ca_bundle))
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), handler)
        try:
            with opener.open(request, timeout=self.timeout) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            try:
                value = json.loads(exc.read())
                detail = value.get("error", str(exc))
            except ValueError:
                detail = str(exc)
            raise RuntimeError(detail) from exc
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Collaboration request failed"))
        return result["data"]

    def connect(self, client="custom-agent", session_id="", capabilities=None):
        return self.call("session.connect", client=client, session_id=session_id, capabilities=capabilities or {})

    def heartbeat(self):
        return self.call("session.heartbeat")

    def claim(self, limit=1):
        return self.call("inbox.claim", limit=limit)

    def delivered(self, message_id):
        return self.call("delivery.ack", message_id=message_id, stage="delivered")

    def read(self, message_id):
        return self.call("delivery.ack", message_id=message_id, stage="read")

    def send(self, targets, text, mode="send", client_id=None):
        return self.call("message.send", targets=targets, text=text, mode=mode, client_id=client_id or uuid.uuid4().hex)

    def reply(self, message_id, text, mode="send", client_id=None):
        return self.call("message.reply", reply_to=message_id, text=text, mode=mode, client_id=client_id or uuid.uuid4().hex)
