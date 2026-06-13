@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Readable GUI を単体の exe にビルドする（PyInstaller 使用）
REM 完成後 dist\Readable.exe をダブルクリックで起動できます。

where python >nul 2>nul
if errorlevel 1 (
  echo Python が見つかりません。https://www.python.org/downloads/ から導入してください
  pause
  exit /b 1
)

if not exist ".venv" (
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
echo 依存パッケージと PyInstaller を準備中...
python -m pip install --quiet --upgrade pip
pip install --quiet -r "backend\requirements.txt"
pip install --quiet pyinstaller

echo Readable.exe をビルドします（数分かかります）...
pyinstaller --noconfirm --onefile --windowed --name Readable ^
  --paths backend ^
  --hidden-import pdf_export --hidden-import pdf_processor --hidden-import translator ^
  --hidden-import deep_translator ^
  --collect-all fitz ^
  --collect-all deep_translator ^
  gui.py

if errorlevel 1 (
  echo.
  echo ✕ ビルドに失敗しました。上のログを確認してください。
  pause
  exit /b 1
)

echo.
echo ============================================
echo  完成: dist\Readable.exe
echo ============================================
echo  ・Google翻訳エンジンはそのまま使えます（無料・キー不要）
echo  ・Ollama を使う場合は setup.bat で Ollama 本体とモデルを導入してください
echo  ・スキャンPDFのOCRには Tesseract が必要です
echo.
pause
