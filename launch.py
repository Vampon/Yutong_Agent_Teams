from yutong_teams.__main__ import main

if __name__ == "__main__":
    import logging
    import sys
    try:
        sys.exit(main())
    except Exception as exc:
        logging.exception("Application failed")
        if sys.stderr:
            print(str(exc), file=sys.stderr)
        else:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "Yutong Agent Teams 启动失败", 0x10)
        sys.exit(1)
