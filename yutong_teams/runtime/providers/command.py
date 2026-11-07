import subprocess
import threading
from ..processes import executable, external_popen, kill, Cancelled, WindowsJob


class CommandAdapter:
    def __init__(self, config, agent, session, binding, persist):
        self.config, self.agent, self.binding = config, agent, binding
        self.proc = None
        self.job = None

    def run(self, prompt, turn, stop, emit, approve):
        import os
        command = executable(self.agent.get("command"), "command") + self.agent.get("args", [])
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        self.proc = external_popen(command, cwd=self.binding["workspace"],
            env=dict(os.environ, PYTHONIOENCODING="utf-8"), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
        proc = self.proc
        self.job = WindowsJob(proc)
        result, overflow, written = {"out": bytearray(), "err": bytearray()}, threading.Event(), threading.Event()
        def read(stream, key):
            try:
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    remaining = 1_000_000 - len(result[key])
                    result[key].extend(chunk[:max(0, remaining)])
                    if len(chunk) > remaining:
                        overflow.set()
                        break
            except (OSError, ValueError):
                pass
        def write():
            try:
                proc.stdin.write((prompt + "\n").encode("utf-8"))
                proc.stdin.close()
                written.set()
            except (OSError, ValueError):
                pass
        readers = [threading.Thread(target=read, args=(proc.stdout, "out"), daemon=True),
                   threading.Thread(target=read, args=(proc.stderr, "err"), daemon=True)]
        writer = threading.Thread(target=write, daemon=True)
        for thread in readers + [writer]:
            thread.start()
        import time
        deadline = time.monotonic() + int(self.agent.get("timeout") or 600)
        try:
            accepted = False
            while proc.poll() is None or any(t.is_alive() for t in readers):
                if overflow.is_set():
                    raise ValueError("命令行输出超过 1 MB，请缩小结果范围")
                if written.is_set() and not accepted:
                    emit("accepted", {}); accepted = True
                if stop.wait(.1):
                    raise Cancelled("程序已停止；请核对已执行操作")
                if time.monotonic() > deadline:
                    raise TimeoutError("命令行执行超时")
            if overflow.is_set():
                raise ValueError("命令行输出超过 1 MB，请缩小结果范围")
            if not accepted:
                emit("accepted", {})
            if proc.returncode:
                raise RuntimeError(result["err"].decode("utf-8", "replace")[-3000:] or "进程退出码 %s" % proc.returncode)
            text = result["out"].decode("utf-8", "replace").strip()
            if not text or len(text) > 100000:
                raise ValueError("命令行返回为空或超过 100000 字符")
            return text
        finally:
            self.close()
            for thread in readers + [writer]:
                thread.join(timeout=1)

    def close(self):
        if self.job:
            self.job.close()
        if self.proc:
            kill(self.proc)
            for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass
