"""
Entry point for the ContribNow desktop app.

Starts the local FastAPI server on localhost:8000, then opens the browser.
This file is the PyInstaller target — `pyinstaller ContribNow.spec` produces
dist/ContribNow.exe from it.
"""

import sys
import threading
import time
import webbrowser

import uvicorn

HOST = "localhost"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _open_browser() -> None:
    # Give uvicorn a moment to start before launching the browser
    time.sleep(1.5)
    webbrowser.open(URL)


def main() -> None:
    print(f"Starting ContribNow at {URL} ...")
    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
