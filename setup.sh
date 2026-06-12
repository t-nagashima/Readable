#!/usr/bin/env bash
# Readable 実行環境を一発で構築するスクリプト。
#   - Python 仮想環境 + 依存パッケージ
#   - Tesseract (OCR, 任意)
#   - Ollama 本体のインストール・起動・モデル取得
#
# 使い方:
#   ./setup.sh                 # 既定モデル(qwen2.5)で構築
#   ./setup.sh gemma2          # 別モデルで構築
#   OLLAMA_MODEL=aya ./setup.sh

set -e
cd "$(dirname "$0")"

MODEL="${1:-${OLLAMA_MODEL:-qwen2.5}}"
OS="$(uname -s)"

bold() { printf "\033[1m%s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }

has() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
bold "==> 1/4 Python 仮想環境と依存パッケージ"
if ! has python3; then
  echo "python3 が見つかりません。先に Python 3 をインストールしてください。"
  exit 1
fi
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  ok "仮想環境を作成しました (.venv)"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt
ok "依存パッケージをインストールしました"

# ---------------------------------------------------------------------------
bold "==> 2/4 Tesseract (OCR / 任意)"
if has tesseract; then
  ok "インストール済み ($(tesseract --version 2>&1 | head -1))"
else
  if [ "$OS" = "Linux" ] && has apt-get; then
    warn "未インストール。apt で導入を試みます（sudo が必要な場合があります）"
    (sudo apt-get update -qq && sudo apt-get install -y -qq tesseract-ocr) \
      && ok "Tesseract を導入しました" \
      || warn "自動導入に失敗。スキャンPDFを使う場合は手動で導入してください"
  elif [ "$OS" = "Darwin" ] && has brew; then
    warn "未インストール。brew で導入します"
    brew install tesseract && ok "Tesseract を導入しました" || warn "導入に失敗しました"
  else
    warn "自動導入できませんでした。スキャンPDFのOCRを使う場合は手動で導入してください"
    warn "  Ubuntu/Debian: sudo apt-get install -y tesseract-ocr"
    warn "  macOS:         brew install tesseract"
  fi
fi

# ---------------------------------------------------------------------------
bold "==> 3/4 Ollama 本体"
if has ollama; then
  ok "インストール済み ($(ollama --version 2>&1 | head -1))"
else
  if [ "$OS" = "Linux" ]; then
    warn "未インストール。公式インストーラで導入します"
    curl -fsSL https://ollama.com/install.sh | sh
    ok "Ollama を導入しました"
  elif [ "$OS" = "Darwin" ]; then
    if has brew; then
      brew install ollama && ok "Ollama を導入しました"
    else
      echo "  Homebrew が見つかりません。https://ollama.com/download から導入してください。"
      exit 1
    fi
  else
    echo "  このOSでは自動導入できません。https://ollama.com/download を参照してください。"
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
bold "==> 4/4 Ollama サーバ起動 & モデル取得"
# サーバが起動しているか確認、なければバックグラウンド起動
if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama サーバは起動済み"
else
  warn "Ollama サーバを起動します (バックグラウンド)"
  nohup ollama serve >/tmp/ollama-serve.log 2>&1 &
  # 起動待ち
  for _ in $(seq 1 20); do
    sleep 1
    if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then break; fi
  done
  if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    ok "Ollama サーバを起動しました (ログ: /tmp/ollama-serve.log)"
  else
    warn "サーバ起動を確認できませんでした。手動で 'ollama serve' を実行してください"
  fi
fi

echo "  モデル '$MODEL' を取得します（初回は時間がかかります）..."
ollama pull "$MODEL" && ok "モデル '$MODEL' を取得しました"

# ---------------------------------------------------------------------------
echo
bold "🎉 セットアップ完了"
echo "次のように実行できます（仮想環境を有効化してから）:"
echo
echo "    source .venv/bin/activate"
echo "    python readable.py paper.pdf --model $MODEL"
echo "    python readable.py ./papers -o ./out --model $MODEL"
echo
echo "Webアプリとして使う場合: ./run.sh"
