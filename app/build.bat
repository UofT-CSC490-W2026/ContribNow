@echo off
setlocal

echo ============================================================
echo  ContribNow — build script
echo  Run from the repo root or from the app/ directory.
echo ============================================================

:: Resolve paths relative to this script regardless of where it's called from
set SCRIPT_DIR=%~dp0
set FRONTEND_DIR=%SCRIPT_DIR%frontend
set FRONTEND_DIST_SRC=%FRONTEND_DIR%\dist
set FRONTEND_DIST_DST=%SCRIPT_DIR%frontend_dist

:: ── Step 1: Build the React frontend ────────────────────────────────────────
echo.
echo [1/3] Building React frontend...
pushd "%FRONTEND_DIR%"
call npx vite build
if errorlevel 1 (echo ERROR: vite build failed & exit /b 1)
popd

:: ── Step 2: Copy dist into app/frontend_dist ────────────────────────────────
echo.
echo [2/3] Copying frontend dist to app\frontend_dist...
if exist "%FRONTEND_DIST_DST%" rmdir /s /q "%FRONTEND_DIST_DST%"
xcopy /e /i /q "%FRONTEND_DIST_SRC%" "%FRONTEND_DIST_DST%"
if errorlevel 1 (echo ERROR: xcopy failed & exit /b 1)

:: ── Step 3: Run PyInstaller ──────────────────────────────────────────────────
echo.
echo [3/3] Running PyInstaller...
pushd "%SCRIPT_DIR%"
pip install -r requirements.txt -q
if errorlevel 1 (echo ERROR: pip install failed & exit /b 1)
pyinstaller ContribNow.spec --noconfirm
if errorlevel 1 (echo ERROR: PyInstaller failed & exit /b 1)
popd

echo.
echo ============================================================
echo  Done!  Executable: app\dist\ContribNow.exe
echo ============================================================
endlocal
