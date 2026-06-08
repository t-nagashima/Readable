# 📄 Readable

英語のPDF論文を、**レイアウトを保ったまま日本語論文のように**読めるようにするWebサービス。
[Readable](https://readable.jp/) のようなツールのオープン実装です。

翻訳は**無料・APIキー不要**（Google翻訳の無料エンドポイント）で動作します。
ローカルLLM（Ollama）にも切り替え可能です。

---

## ✨ 特長

- **PDFをドラッグ&ドロップ**するだけで日本語化
- **3つの表示モード**
  - **オーバーレイ**: 元論文の図表・レイアウトの上に日本語を重ねて表示（Readable風）
  - **対訳**: 左に原文ページ画像、右に日本語訳
  - **原文**: 元のPDFをそのまま表示
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
├── backend/
│   ├── main.py            # FastAPI アプリ（API + 静的配信）
│   ├── pdf_processor.py   # PyMuPDF でPDF解析・ページ画像化・ブロック抽出
│   ├── translator.py      # 翻訳エンジン（Google / Ollama + キャッシュ）
│   └── requirements.txt
├── frontend/
│   ├── index.html         # UI
│   ├── app.js             # アップロード・表示ロジック
│   └── style.css
├── run.sh                 # ワンコマンド起動
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
| `GET` | `/api/engines` | 利用可能エンジンと Ollama の接続状況・モデル一覧 |
| `POST` | `/api/convert` | PDF(`file`)を変換。`target`(既定`ja`), `max_pages`(既定`0`=全ページ), `engine`(`google`/`ollama`), `model`(Ollama用) |

---

## ⚠️ 注意

- Google翻訳の無料エンドポイントは非公式です。大量・商用利用には公式APIやローカルLLMをご検討ください。
- 翻訳・利用は**著作権・各論文の利用規約の範囲内**で行ってください。
- スキャンPDF（画像のみ）はテキスト抽出できません（OCRは未対応）。
