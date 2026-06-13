@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Readable GUI を起動する（コマンドプロンプトを残さず GUI だけ表示）
REM 初回は仮想環境と依存パッケージを自動セットアップします。

where python >nul 2>nul
if errorlevel 1 (
  echo Python が見つかりません。https://www.python.org/downloads/ から導入してください
  echo ^(インストール時に "Add python.exe to PATH" にチェック^)
  pause
  exit /b 1
)

if not exist ".venv" (
  echo 初回セットアップ中です... しばらくお待ちください
  python -m venv .venv
  call ".venv\Scripts\activate.bat"
  python -m pip install --quiet --upgrade pip
  pip install --quiet -r "backend\requirements.txt"
) else (
  call ".venv\Scripts\activate.bat"
)

REM pythonw はコンソールウィンドウを出さずに GUI を起動する
start "" ".venv\Scripts\pythonw.exe" gui.py
