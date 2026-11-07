import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time
from . import __version__
from .config import Config, home_dir
from .engine import Engine
from .server import serve


def instance_lock(root):
    path = root / "instance.lock"
    stream = open(str(path), "a+b")
    stream.seek(0)
    stream.write(b"0")
    stream.flush()
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return stream


def main():
    parser = argparse.ArgumentParser(description="Yutong Agent Teams — 本地智能体协作工作台")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--home", help="覆盖用户数据目录")
    parser.add_argument("--serve", action="store_true", help="只启动本机 Web 界面")
    parser.add_argument("--worker", action="store_true", help="只提供成员身份绑定的 Agent 接入接口")
    parser.add_argument("--mcp", action="store_true", help="作为成员的 MCP stdio 桥接运行")
    parser.add_argument("--connection", help="成员连接配置文件")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--self-test", action="store_true", help="离线检查程序资源和数据库")
    parser.add_argument("--smoke-gui", action="store_true", help="打开窗口并在 8 秒后退出")
    args = parser.parse_args()
    if args.mcp:
        if not args.connection:
            raise ValueError("MCP 桥接需要 --connection 配置文件")
        from .interfaces.mcp import stdio
        return stdio(args.connection)
    if args.home:
        os.environ["YUTONG_TEAMS_HOME"] = args.home
    root = home_dir()
    root.mkdir(parents=True, exist_ok=True)
    config = Config(root)
    resources = Path(getattr(sys, "_MEIPASS", str(Path(__file__).parent.parent)))
    if (resources / "licenses").is_dir():
        import shutil
        shutil.copytree(str(resources / "licenses"), str(root / "licenses"), dirs_exist_ok=True)
        if (resources / "THIRD_PARTY_NOTICES.md").is_file():
            shutil.copyfile(str(resources / "THIRD_PARTY_NOTICES.md"), str(root / "licenses" / "THIRD_PARTY_NOTICES.md"))
    (root / "workspace").mkdir(exist_ok=True)
    lock = instance_lock(root)
    (root / "logs").mkdir(exist_ok=True)
    handler = RotatingFileHandler(str(root / "logs" / "app.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    if args.self_test:
        from .config import asset, atomic_json
        import yaml
        engine = Engine(config)
        result = {"ok": all(asset(p).exists() for p in ("web/index.html", "web/app.js", "web/dialogs.js", "web/views/chat.js", "web/views/runs.js", "web/runs.css", "web/components.css", "web/tokens.css", "web/assets/app-logo.png", "sdk.py", "bridges/ccu.py", "bridges/yat_run.m")),
                  "version": __version__, "home": str(root), "agents": len(config.data["agents"])}
        result["model_config_parser"] = yaml.safe_load("- id: fixture") == [{"id": "fixture"}]
        result["ok"] = result["ok"] and result["model_config_parser"]
        atomic_json(root / "self-test.json", result)
        engine.close()
        if sys.stdout:
            print(json.dumps(result))
        return 0 if result["ok"] else 1
    if not args.worker and args.host != "127.0.0.1":
        raise ValueError("桌面界面仅监听本机。跨电脑执行请使用 --worker")
    engine = Engine(config)
    server, token = serve(engine, args.host, args.port, worker=args.worker)
    if not args.worker and config.data.get("gateway", {}).get("enabled"):
        engine.gateway.configure(config.data["gateway"], save=False)
    url = "http://127.0.0.1:%s/#%s" % (server.server_port, token)
    try:
        if args.serve or args.worker:
            if sys.stdout:
                print("Worker listening on %s:%s" % (args.host, server.server_port) if args.worker else url, flush=True)
            while True:
                time.sleep(.5)
        else:
            import webview
            window = webview.create_window("Yutong Agent Teams", url, width=1440, height=920, min_size=(1024, 680), background_color="#ffffff", hidden=args.smoke_gui)
            def ready():
                if args.smoke_gui:
                    time.sleep(8)
                    from .config import atomic_json
                    try:
                        title = window.evaluate_js("document.title")
                        text = window.evaluate_js("document.body.innerText")
                        logo_loaded = window.evaluate_js("(() => { const image = document.querySelector('.brand-mark'); return !!image && image.complete && image.naturalWidth > 0; })()")
                        window.evaluate_js("document.querySelector('[data-action=nav-agents]').click()")
                        icons_loaded = False
                        for _ in range(15):
                            icons_loaded = window.evaluate_js("(() => { const images = [...document.querySelectorAll('.avatar-image')]; return images.length >= 4 && images.every(image => image.complete && image.naturalWidth > 0); })()")
                            if icons_loaded:
                                break
                            time.sleep(.2)
                        atomic_json(root / "smoke-gui.json", {"ok": "协作空间" in text and logo_loaded and icons_loaded, "title": title, "backend": "edgechromium", "logo_loaded": logo_loaded, "agent_icons_loaded": icons_loaded})
                    finally:
                        window.destroy()
            webview.start(ready, gui="edgechromium", private_mode=False, storage_path=str(root / "webview"))
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        engine.close()
        lock.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        logging.exception("Application failed")
        if sys.stderr:
            print(str(exc), file=sys.stderr)
        if os.name == "nt" and not sys.stdout:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "Yutong Agent Teams 启动失败", 0x10)
        sys.exit(1)
