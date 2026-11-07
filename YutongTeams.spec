from pathlib import Path
import sys
root = Path(SPECPATH)
datas = [(str(root / 'yutong_teams' / 'web'), 'yutong_teams/web'),
         (str(root / 'yutong_teams' / 'sdk.py'), 'yutong_teams'),
         (str(root / 'yutong_teams' / 'bridges' / 'ccu.py'), 'yutong_teams/bridges'),
         (str(root / 'yutong_teams' / 'bridges' / 'yat_run.m'), 'yutong_teams/bridges')]
if (root / 'THIRD_PARTY_NOTICES.md').exists():
    datas.append((str(root / 'THIRD_PARTY_NOTICES.md'), '.'))
if (root / 'licenses').exists():
    datas.append((str(root / 'licenses'), 'licenses'))
binaries = []
sqlite = Path(sys.base_prefix) / 'Library/bin/sqlite3.dll'
if sqlite.exists():
    binaries.append((str(sqlite), '.'))
a = Analysis([str(root / 'launch.py')], pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=['webview.platforms.winforms','webview.platforms.edgechromium','clr','pythonnet','httpx'],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PyQt5','PyQt6','PySide2','PySide6','qtpy','tkinter','numpy','scipy','pandas','matplotlib','torch','IPython','pytest'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,a.binaries,a.datas,[],name='Yutong Agent Teams',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,disable_windowed_traceback=False,
    argv_emulation=False,target_arch=None,codesign_identity=None,entitlements_file=None,icon=str(root/'assets/app.ico'),version=str(root/'assets/version-info.txt'))
