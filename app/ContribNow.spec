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
REPO_ROOT = HERE.parent
FRONTEND_DIST = HERE / "frontend_dist"
PIPELINE_SRC = REPO_ROOT / "src" / "pipeline"

block_cipher = None

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(HERE), str(REPO_ROOT)],
    binaries=[],
    datas=[
        # Bundle the built React frontend
        (str(FRONTEND_DIST), "frontend_dist"),
        # Bundle the data pipeline
        (str(PIPELINE_SRC), "src/pipeline"),
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
        # Data pipeline
        "src.pipeline.ingest",
        "src.pipeline.transform",
        "src.pipeline.load",
        "src.pipeline.utils",
        "src.pipeline.ast_imports",
        "src.pipeline.ast_utils",
        "src.pipeline.cloud_sync",
        "src.pipeline.chunking",
        "src.pipeline.chunking.interfaces",
        "src.pipeline.chunking.registry",
        "src.pipeline.chunking.strategies",
        "src.pipeline.chunking.ts_base_strategy",
        "src.pipeline.chunking.ts_java_strategy",
        "src.pipeline.chunking.ts_javascript_strategy",
        "src.pipeline.chunking.ts_jsx_strategy",
        "src.pipeline.chunking.ts_py_strategy",
        "src.pipeline.embedding",
        "src.pipeline.embedding.interfaces",
        "src.pipeline.embedding.batcher",
        "src.pipeline.embedding.providers",
        "src.pipeline.embedding.providers.huggingface_provider",
        "src.pipeline.embedding.providers.local_provider",
        "src.pipeline.embedding.providers.openai_provider",
        "src.pipeline.indexing",
        "src.pipeline.indexing.cli",
        "src.pipeline.indexing.indexer",
        "src.pipeline.vector_store",
        "src.pipeline.vector_store.in_memory",
        "src.pipeline.vector_store.interfaces",
        "src.pipeline.vector_store.pgvector",
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
