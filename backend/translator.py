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
    """ローカル LLM (Ollama) を使った翻訳。完全無料・オフライン。

    並列実行で複数ブロックを同時翻訳して高速化する。
    """

    name = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self._host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5")
        try:
            self._concurrency = max(1, int(os.environ.get("OLLAMA_CONCURRENCY", "2")))
        except ValueError:
            self._concurrency = 2

    @property
    def model(self) -> str:
        return self._model

    def translate_batch(self, texts: list[str], target: str) -> list[str]:
        if not texts:
            return []
        if self._concurrency <= 1 or len(texts) == 1:
            return [self._translate_one(t, target) for t in texts]
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            return list(pool.map(lambda t: self._translate_one(t, target), texts))

    def _translate_one(self, text: str, target: str) -> str:
        import urllib.error
        import urllib.request

        lang = "日本語" if target == "ja" else target
        prompt = (
            f"あなたは学術論文の翻訳者です。次の英文を自然で読みやすい{lang}に翻訳してください。"
            "専門用語は適切な訳語を用い、訳文のみを出力してください。"
            "前置き・解説・原文の繰り返しは一切不要です。\n\n"
            f"=== 原文 ===\n{text}\n=== 訳文 ==="
        )
        payload = json.dumps(
            {
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:200]
            raise RuntimeError(
                f"Ollama がエラーを返しました (HTTP {e.code})。"
                f"モデル '{self._model}' を `ollama pull {self._model}` で取得済みか確認してください。{detail}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Ollama ({self._host}) に接続できません。`ollama serve` が起動しているか確認してください。理由: {e.reason}"
            ) from e
        return _clean_llm_output(data.get("response") or "")


def _clean_llm_output(text: str) -> str:
    """LLM 出力から思考タグや余計な前置きを取り除く。"""
    import re

    # <think>...</think> など推論モデルの思考ブロックを除去
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    text = text.strip()
    # 区切りマーカーが残っていたら以降を採用
    if "=== 訳文 ===" in text:
        text = text.split("=== 訳文 ===")[-1].strip()
    return text.strip()


def ollama_status(host: str | None = None) -> dict:
    """Ollama の稼働状況とインストール済みモデル一覧を返す。"""
    import urllib.error
    import urllib.request

    base = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return {"available": True, "host": base, "models": models}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"available": False, "host": base, "models": [], "error": str(e)}


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
_backend_cache: dict[tuple[str, str], object] = {}
_backend_lock = threading.Lock()


def default_backend_name() -> str:
    return os.environ.get("TRANSLATOR_BACKEND", "google").lower()


def make_backend(name: str | None = None, model: str | None = None):
    """名前（とモデル）からバックエンドを生成・キャッシュして返す。"""
    name = (name or default_backend_name()).lower()
    if name == "ollama":
        model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5")
        cache_key = ("ollama", model)
    else:
        name = "google"
        cache_key = ("google", "")
    with _backend_lock:
        if cache_key not in _backend_cache:
            _backend_cache[cache_key] = (
                OllamaBackend(model=model) if name == "ollama" else GoogleBackend()
            )
        return _backend_cache[cache_key]


def get_backend():
    """既定（環境変数）のバックエンド。"""
    return make_backend()


def _cache_namespace(backend) -> str:
    """キャッシュキー用の名前空間。Ollama はモデルごとに分ける。"""
    if getattr(backend, "name", "") == "ollama":
        return f"ollama:{getattr(backend, 'model', '')}"
    return backend.name


def translate_texts(
    texts: list[str],
    target: str = "ja",
    backend_name: str | None = None,
    model: str | None = None,
) -> list[str]:
    """テキストのリストを翻訳。キャッシュ済みのものは再利用する。"""
    backend = make_backend(backend_name, model)
    ns = _cache_namespace(backend)
    results: list[str | None] = [None] * len(texts)
    todo: list[tuple[int, str]] = []

    for i, t in enumerate(texts):
        stripped = t.strip()
        if not stripped:
            results[i] = ""
            continue
        key = _cache_key(stripped, ns, target)
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
            _cache_put(_cache_key(src, ns, target), dst)
        flush_cache()

    return [r if r is not None else "" for r in results]
