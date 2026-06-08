"""翻訳エンジン。

デフォルトは Google 翻訳の無料 Web エンドポイント（deep-translator 経由、
APIキー不要・無料）。環境変数で Ollama (ローカルLLM) にも切り替え可能。

切り替え方:
    TRANSLATOR_BACKEND=google   (デフォルト)
    TRANSLATOR_BACKEND=ollama   OLLAMA_MODEL=qwen2.5  も指定可
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

# ----------------------------------------------------------------------------
# 翻訳結果のキャッシュ（無料エンドポイントへの負荷軽減 & 再翻訳の高速化）
# ----------------------------------------------------------------------------
_CACHE_DIR = Path(os.environ.get("TRANSLATE_CACHE_DIR", Path(__file__).parent / ".cache"))
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_FILE = _CACHE_DIR / "translations.json"
_cache_lock = threading.Lock()

try:
    _cache: dict[str, str] = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
except Exception:
    _cache = {}


def _cache_key(text: str, backend: str, target: str) -> str:
    raw = f"{backend}:{target}:{text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_get(key: str) -> str | None:
    with _cache_lock:
        return _cache.get(key)


def _cache_put(key: str, value: str) -> None:
    with _cache_lock:
        _cache[key] = value
        # 都度ディスク保存は重いので、ある程度たまったら保存
        if len(_cache) % 25 == 0:
            _flush_cache_locked()


def _flush_cache_locked() -> None:
    try:
        _CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def flush_cache() -> None:
    with _cache_lock:
        _flush_cache_locked()


# ----------------------------------------------------------------------------
# バックエンド実装
# ----------------------------------------------------------------------------
class GoogleBackend:
    """deep-translator 経由の Google 翻訳（無料・APIキー不要）。"""

    name = "google"

    def __init__(self) -> None:
        from deep_translator import GoogleTranslator

        self._cls = GoogleTranslator
        # GoogleTranslator は 1 リクエスト約 5000 文字まで
        self._limit = 4500

    def translate_batch(self, texts: list[str], target: str) -> list[str]:
        translator = self._cls(source="en", target=target)
        out: list[str] = []
        for t in texts:
            out.append(self._translate_one(translator, t))
        return out

    def _translate_one(self, translator, text: str) -> str:
        if len(text) <= self._limit:
            return translator.translate(text) or ""
        # 長文は文単位で分割して翻訳
        parts = _split_for_limit(text, self._limit)
        return " ".join(translator.translate(p) or "" for p in parts)


class OllamaBackend:
    """ローカル LLM (Ollama) を使った翻訳。完全無料・オフライン。"""

    name = "ollama"

    def __init__(self) -> None:
        self._host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._model = os.environ.get("OLLAMA_MODEL", "qwen2.5")

    def translate_batch(self, texts: list[str], target: str) -> list[str]:
        return [self._translate_one(t, target) for t in texts]

    def _translate_one(self, text: str, target: str) -> str:
        import urllib.request

        lang = "日本語" if target == "ja" else target
        prompt = (
            f"次の学術論文の英文を自然な{lang}に翻訳してください。"
            "訳文だけを出力し、余計な説明・前置きは一切付けないでください。\n\n"
            f"{text}"
        )
        payload = json.dumps(
            {"model": self._model, "prompt": prompt, "stream": False}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return (data.get("response") or "").strip()


def _split_for_limit(text: str, limit: int) -> list[str]:
    """文字数上限を超えないように、なるべく文の区切りで分割する。"""
    import re

    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        if len(cur) + len(s) + 1 <= limit:
            cur = f"{cur} {s}".strip()
        else:
            if cur:
                chunks.append(cur)
            # 1文が上限超えなら強制分割
            while len(s) > limit:
                chunks.append(s[:limit])
                s = s[limit:]
            cur = s
    if cur:
        chunks.append(cur)
    return chunks


# ----------------------------------------------------------------------------
# 公開 API
# ----------------------------------------------------------------------------
_backend = None
_backend_lock = threading.Lock()


def get_backend():
    global _backend
    with _backend_lock:
        if _backend is None:
            name = os.environ.get("TRANSLATOR_BACKEND", "google").lower()
            if name == "ollama":
                _backend = OllamaBackend()
            else:
                _backend = GoogleBackend()
        return _backend


def translate_texts(texts: list[str], target: str = "ja") -> list[str]:
    """テキストのリストを翻訳。キャッシュ済みのものは再利用する。"""
    backend = get_backend()
    results: list[str | None] = [None] * len(texts)
    todo: list[tuple[int, str]] = []

    for i, t in enumerate(texts):
        stripped = t.strip()
        if not stripped:
            results[i] = ""
            continue
        key = _cache_key(stripped, backend.name, target)
        cached = _cache_get(key)
        if cached is not None:
            results[i] = cached
        else:
            todo.append((i, stripped))

    if todo:
        translated = backend.translate_batch([t for _, t in todo], target)
        for (i, src), dst in zip(todo, translated):
            dst = dst or ""
            results[i] = dst
            _cache_put(_cache_key(src, backend.name, target), dst)
        flush_cache()

    return [r if r is not None else "" for r in results]
