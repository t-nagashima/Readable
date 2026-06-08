"""Readable クローン — 英語PDF論文を日本語論文のように読めるようにするサービス。

エンドポイント:
    GET  /                ... フロントエンド (静的ファイル)
    POST /api/convert     ... PDF をアップロードして変換（解析+翻訳）
    GET  /api/health      ... 稼働確認 & 現在の翻訳バックエンド
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import pdf_processor
import translator

app = FastAPI(title="Readable", description="英語論文を日本語論文のように変換")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# アップロードサイズ上限（MB）
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "30"))


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "default_backend": translator.default_backend_name(),
    }


@app.get("/api/engines")
def engines():
    """利用可能な翻訳エンジンと、Ollama の状態・モデル一覧を返す。"""
    ollama = translator.ollama_status()
    return {
        "default": translator.default_backend_name(),
        "engines": ["google", "ollama"],
        "ollama": ollama,
    }


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    target: str = Form("ja"),
    max_pages: int = Form(0),
    engine: str = Form(""),
    model: str = Form(""),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDFファイルをアップロードしてください。")

    data = await file.read()
    size_mb = len(data) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise HTTPException(
            status_code=413,
            detail=f"ファイルが大きすぎます（上限 {MAX_UPLOAD_MB}MB）。",
        )

    try:
        result = pdf_processor.process_pdf(data, max_pages=max_pages)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"PDFの解析に失敗しました: {e}")

    backend_name = engine.strip().lower() or None
    model_name = model.strip() or None

    # 各ページのブロックをまとめて翻訳
    try:
        for page in result["pages"]:
            sources = [b["source"] for b in page["blocks"]]
            translations = translator.translate_texts(
                sources, target=target, backend_name=backend_name, model=model_name
            )
            for b, tr in zip(page["blocks"], translations):
                b["target"] = tr
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"翻訳に失敗しました: {e}")

    used = translator.make_backend(backend_name, model_name)
    result["filename"] = file.filename
    result["engine"] = getattr(used, "name", "google")
    result["model"] = getattr(used, "model", None)
    return JSONResponse(result)


# --- 静的フロントエンドの配信 -------------------------------------------------
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        reload=bool(os.environ.get("DEV")),
    )
