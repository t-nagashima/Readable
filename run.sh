#!/usr/bin/env bash
# Readable をローカルで起動するスクリプト
set -e

cd "$(dirname "$0")"

# 仮想環境（初回のみ作成）
if [ ! -d ".venv" ]; then
  echo "==> 仮想環境を作成中..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> 依存パッケージをインストール中..."
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

echo "==> サーバーを起動します -> http://127.0.0.1:8000"
cd backend
exec python main.py
