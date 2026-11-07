"""Owned external processes; no collaboration semantics live here."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time

_launch_lock = threading.Lock()

class Cancelled(Exception):
    pass

def external_popen(command, **kwargs):
    """Do not make independently installed agents load our bundled DLLs."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return subprocess.Popen(command, **kwargs)
    import ctypes
    env = dict(kwargs.get("env") or os.environ)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    bundle = os.path.normcase(os.path.abspath(sys._MEIPASS))
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                 if not os.path.normcase(os.path.abspath(p)).startswith(bundle + os.sep)
                                 and os.path.normcase(os.path.abspath(p)) != bundle)
    kwargs["env"] = env
    with _launch_lock:
        previous = ctypes.create_unicode_buffer(32768)
        ctypes.windll.kernel32.GetDllDirectoryW(len(previous), previous)
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        try:
            return subprocess.Popen(command, **kwargs)
        finally:
            ctypes.windll.kernel32.SetDllDirectoryW(previous.value or None)

def executable(command, kind=""):
    command = command or kind
    found = shutil.which(command) or (command if Path(command).is_file() else "")
    if not found:
        # Windows GUI processes may inherit PATH before npm was installed.
        for suffix in (".exe", ".cmd", ".ps1"):
            path = Path(os.environ.get("APPDATA", "")) / "npm" / (command + suffix)
            if path.is_file():
                found = str(path)
                break
    if not found:
        raise ValueError("找不到可执行程序：" + command)
    if Path(found).suffix.lower() in (".cmd", ".bat", ".ps1"):
        package = {"claude": ("@anthropic-ai/claude-code", "claude"), "deepseek": ("@deepseek-ai/dsh", "dsh")}.get(kind)
        if not package:
            raise ValueError("请指定原生程序，或 python.exe / node.exe 和参数；不执行 shell 包装脚本")
        root = Path(found).parent / "node_modules" / package[0]
        data = json.loads((root / "package.json").read_text("utf-8"))
        entry = data["bin"] if isinstance(data["bin"], str) else data["bin"][package[1]]
        if Path(entry).suffix.lower() == ".exe":
            return [str(root / entry)]
        node = shutil.which("node")
        if not node:
            raise ValueError("找不到 Node.js，请在成员设置填写原生 CLI 路径")
        return [node, str(root / entry)]
    return [found]

def kill(proc):
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    else:
        import signal
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def own_windows_job(proc):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    class Limits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_longlong), ("job_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t),
                    ("active", wintypes.DWORD), ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in ("ro", "wo", "oo", "rb", "wb", "ob")]
    class Extended(ctypes.Structure):
        _fields_ = [("limits", Limits), ("io", IO), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
    kernel = ctypes.windll.kernel32
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    info = Extended(); info.limits.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)) or not kernel.AssignProcessToJobObject(job, int(proc._handle)):
        if job:
            kernel.CloseHandle(job)
        kill(proc)
        raise RuntimeError("无法建立 Windows 子进程生命周期约束")
    return job

class WindowsJob:
    def __init__(self, proc):
        self.handle = own_windows_job(proc)
        self.lock = threading.Lock()

    def close(self):
        with self.lock:
            if self.handle:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self.handle)
                self.handle = None


class ProcessChannel:
    """A long-lived line protocol with bounded IO and owned process lifetime."""
    def __init__(self, command, cwd, env=None):
        child_env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        child_env.update(env or {})
        child_env.pop("CLAUDECODE", None)
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
        self.proc = external_popen(command, cwd=cwd, env=child_env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, **flags)
        self.events = queue.Queue(maxsize=1000)
        self.closed = threading.Event()
        self.errors = []
        self.lock = threading.Lock()
        self.job = WindowsJob(self.proc)
        for stream, channel in ((self.proc.stdout, "out"), (self.proc.stderr, "err")):
            threading.Thread(target=self._read, args=(stream, channel), daemon=True).start()

    def _put(self, value):
        while not self.closed.is_set():
            try:
                self.events.put(value, timeout=.2)
                return
            except queue.Full:
                pass

    def _read(self, stream, channel):
        try:
            while not self.closed.is_set():
                raw = stream.readline(4_000_001)
                if not raw:
                    break
                if len(raw) > 4_000_000:
                    self._put(("fatal", "单条运行事件超过 4 MB"))
                    break
                line = raw.decode("utf-8", "replace").rstrip()
                if channel == "err":
                    self.errors.append(line)
                    self.errors = self.errors[-25:]
                else:
                    self._put((channel, line))
        except (OSError, ValueError):
            pass
        finally:
            self._put((channel, None))

    def send(self, value):
        data = (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8")
        if len(data) > 1_000_000:
            raise ValueError("运行输入超过 1 MB")
        errors, finished = [], threading.Event()
        def write():
            try:
                with self.lock:
                    self.proc.stdin.write(data)
                    self.proc.stdin.flush()
            except Exception as exc:
                errors.append(exc)
            finally:
                finished.set()
        threading.Thread(target=write, daemon=True).start()
        if not finished.wait(10):
            self.close()
            raise TimeoutError("运行器没有读取输入；投递结果不确定")
        if errors:
            raise RuntimeError("运行器输入通道关闭：" + str(errors[0]))

    def next(self, stop, deadline):
        while True:
            if stop.is_set():
                self.close()
                raise Cancelled("已停止运行；请核对尚未确认的投递")
            if time.monotonic() > deadline:
                self.close()
                raise TimeoutError("运行器超时；未自动重放消息")
            try:
                channel, line = self.events.get(timeout=.15)
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise RuntimeError("运行器已退出：" + "\n".join(self.errors)[-3000:])
                continue
            if channel == "fatal":
                self.close()
                raise RuntimeError(line)
            if line is None:
                if channel == "out":
                    raise RuntimeError("运行器输出通道关闭：" + "\n".join(self.errors)[-3000:])
                continue
            if line.startswith("YAT_EVENT "):
                line = line[10:]
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    return event
            except ValueError:
                pass

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        if self.job:
            self.job.close()
        kill(self.proc)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass
