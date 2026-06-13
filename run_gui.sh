#!/usr/bin/env bash
# Readable GUI を起動する（macOS / Linux）。初回は依存を自動セットアップ。
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "初回セットアップ中..."
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r backend/requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec python gui.py
