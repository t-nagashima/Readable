@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM Readable 実行環境を一発構築するスクリプト (Windows / cmd 用)
REM   - Python 仮想環境 + 依存パッケージ
REM   - Tesseract (OCR, 任意)
REM   - Ollama 本体のインストール・起動・モデル取得
REM
REM 使い方:  setup.bat            (既定モデル qwen2.5)
REM          setup.bat gemma2     (モデル指定)

set "MODEL=%~1"
if "%MODEL%"=="" set "MODEL=qwen2.5"

echo ============================================
echo  Readable セットアップ (Windows)
echo  モデル: %MODEL%
echo ============================================
echo.

REM ---------------------------------------------------------------------------
echo [1/4] Python 仮想環境と依存パッケージ
where python >nul 2>nul
if errorlevel 1 (
  echo   x Python が見つかりません。
  echo     https://www.python.org/downloads/ から導入してください
  echo     ^(インストール時に "Add python.exe to PATH" にチェック^)
  goto :end
)
if not exist ".venv" (
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python -m pip install --quiet --upgrade pip
pip install --quiet -r "backend\requirements.txt"
if errorlevel 1 (
  echo   x 依存パッケージのインストールに失敗しました
  goto :end
)
echo   o 依存パッケージをインストールしました
echo.

REM ---------------------------------------------------------------------------
echo [2/4] Tesseract (OCR / 任意)
where tesseract >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if errorlevel 1 (
    echo   ! winget が無いため自動導入をスキップします
    echo     スキャンPDFを使う場合は手動で導入してください:
    echo     https://github.com/UB-Mannheim/tesseract/wiki
  ) else (
    echo   ! winget で Tesseract を導入します...
    winget install -e --id UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements
  )
) else (
  echo   o インストール済み
)
echo.

REM ---------------------------------------------------------------------------
echo [3/4] Ollama 本体
set "OLLAMA_EXE=ollama"
where ollama >nul 2>nul
if errorlevel 1 (
  where winget >nul 2>nul
  if errorlevel 1 (
    echo   x winget が無いため自動導入できません
    echo     https://ollama.com/download/windows から導入してください
    goto :end
  )
  echo   ! winget で Ollama を導入します...
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
  REM 導入直後は PATH が未反映のため、既定パスの exe を直接使う
  if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
) else (
  echo   o インストール済み
)
echo.

REM ---------------------------------------------------------------------------
echo [4/4] Ollama サーバ起動 ^& モデル取得
curl -s --max-time 2 http://localhost:11434/api/tags >nul 2>nul
if errorlevel 1 (
  echo   ! Ollama サーバを起動します...
  start "" "%OLLAMA_EXE%" serve
  timeout /t 6 /nobreak >nul
) else (
  echo   o Ollama サーバは起動済み
)
echo   モデル '%MODEL%' を取得します ^(初回は時間がかかります^)...
"%OLLAMA_EXE%" pull %MODEL%
if errorlevel 1 (
  echo   ! モデル取得に失敗しました。新しいコマンドプロンプトを開いて
  echo     "ollama pull %MODEL%" を実行してみてください
)
echo.

echo ============================================
echo  セットアップ完了
echo ============================================
echo  次のように実行できます:
echo.
echo    .venv\Scripts\python.exe readable.py paper.pdf --model %MODEL%
echo    .venv\Scripts\python.exe readable.py .\papers -o .\out --model %MODEL%
echo.
echo  ^(仮想環境を有効化してから使う場合^)
echo    call .venv\Scripts\activate.bat
echo    python readable.py paper.pdf --model %MODEL%
echo.

:end
endlocal
pause
