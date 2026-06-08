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

デフォルトは Google 翻訳（無料・キー不要）。環境変数で変更できます。

### ローカルLLM (Ollama) を使う（完全無料・オフライン）

```bash
# 事前に Ollama をインストールしてモデルを取得
#   https://ollama.com/
ollama pull qwen2.5

# Ollama バックエンドで起動
TRANSLATOR_BACKEND=ollama OLLAMA_MODEL=qwen2.5 python backend/main.py
```

| 環境変数 | 既定値 | 説明 |
| --- | --- | --- |
| `TRANSLATOR_BACKEND` | `google` | `google` または `ollama` |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama のホスト |
| `OLLAMA_MODEL` | `qwen2.5` | 使用するモデル名 |
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
| `GET` | `/api/health` | 稼働確認・現在の翻訳バックエンド |
| `POST` | `/api/convert` | PDF(`file`)をアップロードして変換。`target`(既定`ja`), `max_pages`(既定`0`=全ページ) |

---

## ⚠️ 注意

- Google翻訳の無料エンドポイントは非公式です。大量・商用利用には公式APIやローカルLLMをご検討ください。
- 翻訳・利用は**著作権・各論文の利用規約の範囲内**で行ってください。
- スキャンPDF（画像のみ）はテキスト抽出できません（OCRは未対応）。
