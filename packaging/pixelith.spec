# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
datas = [
    (str(root / "web"), "web"),
    (str(root / "LICENSE"), "."),
    (str(root / "NOTICE.md"), "."),
]
hiddenimports = []
binaries = []
for package in ("webview", "uvicorn", "onnxruntime"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

a = Analysis(
    [str(root / "pixelith" / "desktop.py")],
    pathex=[str(root)], binaries=binaries, datas=datas,
    hiddenimports=hiddenimports, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Pixelith",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Pixelith")
if sys.platform == "darwin":
    app = BUNDLE(
        coll, name="Pixelith.app", bundle_identifier="solutions.pgatech.pixelith",
        info_plist={
            "CFBundleShortVersionString": "0.41b2",
            "CFBundleVersion": "0.41.2",
            "NSHighResolutionCapable": True,
        },
    )
