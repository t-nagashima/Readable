# 📄 Readable

英語のPDF論文を、**レイアウトを保ったまま日本語論文のように**読めるようにするツール。
[Readable](https://readable.jp/) のようなツールのオープン実装です。

**コマンドライン（CLI）** と **Webアプリ** の両方で使えます。
翻訳は**無料・APIキー不要**（Google翻訳の無料エンドポイント）か、ローカルLLM（Ollama）で動作します。

---

## ⚡ クイックスタート（CLI / Ollama）

### macOS / Linux

```bash
# 1) 実行環境を一発構築（Python依存 + Tesseract + Ollama + モデル取得）
./setup.sh

# 2) 仮想環境を有効化して変換
source .venv/bin/activate
python readable.py paper.pdf                 # → paper_ja.pdf
python readable.py ./papers -o ./out         # フォルダ一括 → 個別出力
python readable.py paper.pdf --mode both     # 日本語のみ + 英日交互の両方
```

### Windows（コマンドプロンプト）

> ⚠️ `setup.sh` は bash 用なので **Windows の cmd では動きません**。
> Windows では **`setup.bat`** を使ってください（ダブルクリック、または cmd で実行）。

```bat
REM 1) 実行環境を一発構築（Python依存 + Tesseract + Ollama + モデル取得）
setup.bat

REM 2) 変換（仮想環境のpythonを直接呼ぶのが簡単）
.venv\Scripts\python.exe readable.py paper.pdf
.venv\Scripts\python.exe readable.py .\papers -o .\out
.venv\Scripts\python.exe readable.py paper.pdf --mode both
```

- 事前に [Python](https://www.python.org/downloads/) が必要です（インストール時に **「Add python.exe to PATH」にチェック**）。
- Ollama / Tesseract の自動導入には **winget**（Windows 10/11 標準）を使います。無い場合は画面の案内に従って手動導入してください。
- `setup.bat` で Ollama を新規導入した直後は、いったん**ウィンドウを閉じて開き直す**と `ollama` コマンドが使えるようになります。

---

## 🖥 CLI の使い方

ブラウザ不要。1ファイル指定でも、フォルダまるごと一括でも変換できます。

```bash
python readable.py <PDFファイル or フォルダ> [オプション]
```

| オプション | 既定 | 説明 |
| --- | --- | --- |
| `--mode {ja,alt,both}` | `ja` | `ja`=日本語のみ / `alt`=英日交互 / `both`=両方 |
| `--engine {ollama,google}` | `ollama` | 翻訳エンジン |
| `--model NAME` | `qwen2.5` | Ollama のモデル名 |
| `--ocr {auto,force,off}` | `auto` | スキャンPDFのOCR |
| `-o, --output DIR` | 入力と同じ場所 | 出力先フォルダ |
| `-r, --recursive` | - | フォルダを再帰的に探索 |
| `--pages N` | `0`(全部) | 先頭Nページのみ |

出力ファイル名は `元ファイル名_ja.pdf` / `元ファイル名_bilingual.pdf` になります。

```bash
# 例: フォルダを再帰探索し、Google翻訳（無料）で日本語化
python readable.py ./papers -r --engine google -o ./out

# 例: スキャンPDFを常にOCRして英日交互で出力
python readable.py scan.pdf --ocr force --mode alt
```

### 環境構築（`./setup.sh`）

`setup.sh` が以下を自動で行います（OSを判別、冪等）。

1. Python 仮想環境 `.venv` + 依存パッケージ
2. Tesseract（OCR・任意）
3. **Ollama 本体のインストール・サーバ起動・モデル取得**

```bash
./setup.sh            # 既定モデル qwen2.5
./setup.sh gemma2     # 別モデルを指定
```

---

## ✨ 特長

- **CLI / Web** の両対応（CLIはフォルダ一括変換が可能）
- **PDFをドラッグ&ドロップ**するだけで日本語化（Web）
- **3つの表示モード**
  - **オーバーレイ**: 元論文の図表・レイアウトの上に日本語を重ねて表示（Readable風）
  - **対訳**: 左に原文ページ画像、右に日本語訳
  - **原文**: 元のPDFをそのまま表示
- **翻訳PDFのダウンロード**
  - **日本語のみ**: 原文のレイアウトを保ったまま英文を日本語に置換
  - **英日交互ページ**: 英文ページと日本語ページを交互に並べた対訳冊子
- **OCR対応**: スキャンPDF（画像のみ）も文字認識して翻訳（Tesseract）
- **無料**で動く翻訳エンジン（APIキー不要）
- 翻訳結果を**キャッシュ**して再変換を高速化
- 図・数式・表はそのまま画像として保持

---

## 🚀 使い方

### かんたん起動（推奨）

```bash
./run.sh
```

ブラウザで http://127.0.0.1:8000 を開く。

### 手動で起動する場合

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
python main.py
```

---

## 🌐 翻訳エンジンの切り替え

エンジンは **画面上のプルダウンで選択**できます（デフォルトは Google 翻訳）。

- **Google翻訳**: 無料・キー不要・高速。すぐ使える。
- **ローカルLLM (Ollama)**: 完全無料・オフライン。論文向けに自然な訳になりやすい。

### ローカルLLM (Ollama) を使う

1. Ollama をインストール: https://ollama.com/
2. モデルを取得して起動:
   ```bash
   ollama pull qwen2.5   # 日本語が得意なモデルの一例
   ollama serve          # 通常はインストール時に自動起動
   ```
3. Readable を起動し、画面の「翻訳エンジン」で **ローカルLLM (Ollama)** を選択。
   - Ollama が起動していれば**接続状況とインストール済みモデルが自動表示**され、モデルを選べます。
   - 接続できない場合は画面に対処方法が表示されます。

> モデルのおすすめ: `qwen2.5`, `gemma2`, `aya` など日本語に強いものが快適です。

### 環境変数（任意）

| 環境変数 | 既定値 | 説明 |
| --- | --- | --- |
| `TRANSLATOR_BACKEND` | `google` | 既定エンジン。`google` または `ollama` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama のホスト |
| `OLLAMA_MODEL` | `qwen2.5` | 既定モデル名 |
| `OLLAMA_CONCURRENCY` | `2` | Ollama 翻訳の並列数 |
| `MAX_UPLOAD_MB` | `30` | アップロード上限(MB) |
| `PORT` | `8000` | サーバーポート |
| `TRANSLATE_CACHE_DIR` | `backend/.cache` | 翻訳キャッシュの保存先 |

---

## 🏗 構成

```
Readable/
├── readable.py            # CLI（1ファイル / フォルダ一括変換）
├── setup.sh               # 環境一発構築（Python + Tesseract + Ollama + モデル）
├── backend/
│   ├── main.py            # FastAPI アプリ（API + 静的配信）
│   ├── pdf_processor.py   # PyMuPDF でPDF解析・OCR・ブロック抽出
│   ├── pdf_export.py      # 翻訳結果から日本語/英日交互PDFを生成
│   ├── translator.py      # 翻訳エンジン（Google / Ollama + キャッシュ）
│   └── requirements.txt
├── frontend/
│   ├── index.html         # UI
│   ├── app.js             # アップロード・表示ロジック
│   └── style.css
├── run.sh                 # Webアプリ起動
└── README.md
```

### しくみ

1. アップロードされたPDFを **PyMuPDF** で解析
2. 各ページを画像化し、テキストブロックを**座標付き**で抽出
3. ブロック単位で英→日に翻訳（キャッシュ利用）
4. フロントで、元ページ画像の上に日本語ブロックを**同じ位置に重ねて**描画

---

## 📡 API

| メソッド | パス | 説明 |
| --- | --- | --- |
| `GET` | `/api/health` | 稼働確認・既定の翻訳バックエンド |
| `GET` | `/api/engines` | 利用可能エンジン・Ollama接続状況・モデル一覧・OCR可否 |
| `POST` | `/api/convert` | PDF(`file`)を変換。`target`(既定`ja`), `max_pages`(既定`0`=全ページ), `engine`(`google`/`ollama`), `model`(Ollama用), `ocr`(`auto`/`force`/`off`) |
| `GET` | `/api/download` | 翻訳PDFを取得。`doc_id`(convertの戻り値), `mode`(`ja`=日本語のみ / `alt`=英日交互) |

## 🔎 OCR（スキャンPDF対応）

テキスト層を持たないスキャンPDFは **Tesseract OCR** で文字認識してから翻訳します。

```bash
# macOS
brew install tesseract
# Ubuntu / Debian
sudo apt-get install -y tesseract-ocr
```

- 画面の「OCR」で `自動`（スキャンを検出して必要時のみ）/ `常にOCR` / `OCRしない` を選択できます。
- 未インストールの場合は画面に案内が表示され、テキスト層のあるPDFのみ処理します。

---

## ⚠️ 注意

- Google翻訳の無料エンドポイントは非公式です。大量・商用利用には公式APIやローカルLLMをご検討ください。
- 翻訳・利用は**著作権・各論文の利用規約の範囲内**で行ってください。
- スキャンPDF（画像のみ）はテキスト抽出できません（OCRは未対応）。
