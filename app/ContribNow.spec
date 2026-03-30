# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for ContribNow.
#
# Build from the app/ directory:
#   pip install -r requirements.txt
#   pyinstaller ContribNow.spec --noconfirm
#
# Output: app/dist/ContribNow.exe

from pathlib import Path

HERE = Path(SPECPATH)  # resolves to app/
FRONTEND_DIST = HERE / "frontend_dist"

block_cipher = None

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(HERE)],
    binaries=[],
    datas=[
        # Bundle the built React frontend
        (str(FRONTEND_DIST), "frontend_dist"),
    ],
    hiddenimports=[
        # uvicorn uses dynamic imports — list them explicitly
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        # FastAPI / starlette internals
        "starlette.routing",
        "starlette.staticfiles",
        "starlette.responses",
        # Our backend package
        "backend",
        "backend.main",
        "backend.models",
        "backend.routes.analyze",
        "backend.routes.snapshot",
        "backend.routes.ask",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="ContribNow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=True keeps a terminal window open — useful while debugging.
    # Set to False for a clean user-facing release.
    console=True,
    icon=None,
)
