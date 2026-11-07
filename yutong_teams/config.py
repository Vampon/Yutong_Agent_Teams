import base64
import copy
import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import threading


def home_dir():
    return Path(os.environ.get("YUTONG_TEAMS_HOME", str(Path.home() / ".yutong-agent-teams"))).resolve()


def asset(name):
    return Path(__file__).parent / name


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temp), str(path))


def protect(value, decrypt=False):
    """Windows CurrentUser DPAPI; credentials never enter exported config."""
    if os.name != "nt":
        raise ValueError("此系统请使用环境变量保存凭据")
    class Blob(ctypes.Structure):
        _fields_ = [("size", ctypes.c_ulong), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value) if decrypt else value.encode("utf-8")
    buf = ctypes.create_string_buffer(raw)
    src = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        result = ctypes.string_at(out.data, out.size)
        return result.decode("utf-8") if decrypt else base64.b64encode(result).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out.data)


def existing(path):
    return path if Path(path).exists() else ""


def defaults():
    python = shutil.which("python") or "python"
    return {"version": 2, "parallel": 3, "permissions": {"mode": "ask", "review": True}, "agents": [
        {"id": "claude", "name": "Claude Code", "kind": "claude", "role": "编程、方案设计与代码评审", "command": "claude", "color": "#9b745a"},
        {"id": "deepseek", "name": "DeepSeek Harness", "kind": "deepseek", "role": "分析、实现与交叉检查", "command": "dsh", "color": "#526cbd"},
        {"id": "ccu", "name": "CCU Agent", "kind": "ccu", "role": "整车控制器研发与工程工具", "project": existing(r"D:\Project\CCU Agent"), "command": python, "color": "#28796d"},
        {"id": "matlab", "name": "MATLAB Agent", "kind": "matlab", "role": "MATLAB、Simulink 与模型验证", "project": existing(r"D:\Project\matlab_ai\ai_sdk\automotive-agent"), "command": existing(r"D:\Program Files\MATLAB\R2026a\bin\matlab.exe") or "matlab", "color": "#b07a28"},
        {"id": "adp", "name": "腾讯 ADP", "kind": "adp", "role": "企业知识与业务智能体", "url": "https://wss.lke.cloud.tencent.com/adp/v2/chat", "secret_env": "YUTONG_ADP_APP_KEY", "user_id": "", "color": "#537c98"}
    ]}


class Config:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "config.json"
        self.lock = threading.RLock()
        if not self.path.exists():
            atomic_json(self.path, defaults())
        self.data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        self.secret_path = self.root / "credentials.json"
        self.secrets = json.loads(self.secret_path.read_text("utf-8")) if self.secret_path.exists() else {}

    def public(self):
        from .core.permissions import effective
        with self.lock:
            data = copy.deepcopy(self.data)
            data.setdefault("permissions", {"mode": "ask", "review": True})
            data["agents"] = [self.agent(a["id"]) for a in data["agents"]]
            for agent in data["agents"]:
                owner = agent.get("source_id") or agent["id"]
                agent["has_secret"] = bool(self.secrets.get(owner) or os.environ.get(agent.get("secret_env", "")))
                agent["permission_effective"] = effective(self, agent["id"])
                if agent.get("source_id"):
                    agent["source_name"] = self.raw_agent(owner)["name"]
            return data

    def raw_agent(self, aid):
        with self.lock:
            for a in self.data["agents"]:
                if a["id"] == aid:
                    return copy.deepcopy(a)
        raise ValueError("找不到成员：" + str(aid))

    def agent(self, aid):
        with self.lock:
            value = self.raw_agent(aid)
            if not value.get("source_id"):
                return value
            source = self.raw_agent(value["source_id"])
            if source.get("source_id") or source["id"] == aid:
                raise ValueError("分身必须引用原始运行器接入，不能循环引用")
            # Share transport configuration, but never source persona/session data.
            for key in ("name", "role", "instructions", "cwd", "timeout", "permission_mode", "auto_tools"):
                source.pop(key, None)
            source.update(value)
            return source

    def secret(self, agent):
        with self.lock:
            env = os.environ.get(agent.get("secret_env", ""))
            if env:
                return env
            value = self.secrets.get(agent.get("source_id") or agent["id"])
            return protect(value, True) if value else ""

    def save_agent(self, value, create=False):
        import re
        a = copy.deepcopy(value)
        secret = a.pop("secret", "")
        clear = a.pop("clear_secret", False)
        for key in ("has_secret", "source_name", "permission_effective"):
            a.pop(key, None)
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", a.get("id", "")):
            raise ValueError("成员 ID 使用小写字母、数字、短横线或下划线，以字母开头")
        if not a.get("name", "").strip():
            raise ValueError("请填写成员名称")
        if not a.get("source_id") and not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", a.get("kind", "")):
            raise ValueError("未知接入类型")
        if not isinstance(a.get("args", []), list) or not all(isinstance(x, str) for x in a.get("args", [])):
            raise ValueError("启动参数必须为 JSON 字符串数组")
        a["timeout"] = min(7200, max(10, int(a.get("timeout") or 600)))
        for key, limit in (("name", 100), ("role", 400), ("instructions", 16000)):
            if not isinstance(a.get(key, ""), str) or len(a.get(key, "")) > limit:
                raise ValueError("%s 内容过长或格式错误" % key)
        if a.get("permission_mode", "inherit") not in ("inherit", "ask", "auto", "deny"):
            raise ValueError("未知成员确认策略")
        with self.lock:
            data = copy.deepcopy(self.data)
            items = data["agents"]
            index = next((i for i, old in enumerate(items) if old["id"] == a["id"]), len(items))
            if create and index < len(items):
                raise ValueError("成员 ID 已存在")
            if index < len(items) and items[index].get("source_id", "") != a.get("source_id", ""):
                raise ValueError("已有成员不能更换分身来源")
            if a.get("source_id"):
                source = self.raw_agent(a["source_id"])
                if not a.get("role", "").strip():
                    raise ValueError("请填写分身职责")
                if source.get("source_id") or source["id"] == a["id"]:
                    raise ValueError("分身必须引用原始运行器接入")
                if secret or clear:
                    raise ValueError("分身共用来源接入的凭据，请在来源设置中修改")
                allowed = ("id", "source_id", "name", "role", "instructions", "cwd", "timeout", "permission_mode", "color")
                a = {k: v for k, v in a.items() if k in allowed}
            if index == len(items):
                items.append(a)
            else:
                items[index] = a
            if secret:
                self.secrets[a["id"]] = protect(secret)
            elif clear:
                self.secrets.pop(a["id"], None)
            atomic_json(self.secret_path, self.secrets)
            atomic_json(self.path, data)
            self.data = data
        return self.agent(a["id"])

    def redact(self, text):
        text = str(text)
        for a in self.data["agents"]:
            try:
                secret = self.secret(a)
                if secret:
                    text = text.replace(secret, "[凭据已隐藏]")
            except Exception:
                pass
        return text
