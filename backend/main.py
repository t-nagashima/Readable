"""Readable クローン — 英語PDF論文を日本語論文のように読めるようにするサービス。

エンドポイント:
    GET  /                ... フロントエンド (静的ファイル)
    POST /api/convert     ... PDF をアップロードして変換（解析+翻訳）
    GET  /api/download    ... 翻訳済みPDFをダウンロード（日本語のみ / 英日交互）
    GET  /api/engines     ... 翻訳エンジン一覧・OCR可否
    GET  /api/health      ... 稼働確認 & 現在の翻訳バックエンド
"""

from __future__ import annotations

import os
import uuid
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import pdf_export
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

# 変換済みドキュメントの一時保管（ダウンロード生成用）。直近 N 件を保持。
_DOC_STORE: "OrderedDict[str, dict]" = OrderedDict()
_DOC_STORE_LIMIT = int(os.environ.get("DOC_STORE_LIMIT", "20"))
_store_lock = Lock()


def _store_doc(doc_id: str, data: bytes, result: dict) -> None:
    with _store_lock:
        _DOC_STORE[doc_id] = {"data": data, "result": result}
        while len(_DOC_STORE) > _DOC_STORE_LIMIT:
            _DOC_STORE.popitem(last=False)


def _get_doc(doc_id: str) -> dict | None:
    with _store_lock:
        return _DOC_STORE.get(doc_id)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "default_backend": translator.default_backend_name(),
    }


@app.get("/api/engines")
def engines():
    """利用可能な翻訳エンジンと、Ollama の状態・OCR可否を返す。"""
    ollama = translator.ollama_status()
    return {
        "default": translator.default_backend_name(),
        "engines": ["google", "ollama"],
        "ollama": ollama,
        "ocr_available": pdf_processor.ocr_available(),
    }


@app.post("/api/convert")
async def convert(
    file: UploadFile = File(...),
    target: str = Form("ja"),
    max_pages: int = Form(0),
    engine: str = Form(""),
    model: str = Form(""),
    ocr: str = Form("auto"),
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

    ocr_mode = ocr.strip().lower()
    if ocr_mode not in ("auto", "force", "off"):
        ocr_mode = "auto"

    try:
        result = pdf_processor.process_pdf(data, max_pages=max_pages, ocr=ocr_mode)
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

    # ダウンロード生成のために原文と結果を一時保管
    doc_id = uuid.uuid4().hex
    _store_doc(doc_id, data, result)
    result["doc_id"] = doc_id

    return JSONResponse(result)


def _download_filename(original: str, mode: str) -> str:
    stem = original[:-4] if original.lower().endswith(".pdf") else original
    suffix = "_bilingual" if mode == "alt" else "_ja"
    # ASCII 以外はファイル名トラブルの元なので簡易サニタイズ
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in stem) or "readable"
    return f"{safe}{suffix}.pdf"


@app.get("/api/download")
def download(doc_id: str, mode: str = "ja"):
    """翻訳済みPDFを生成して返す。mode: 'ja'(日本語のみ) / 'alt'(英日交互)。"""
    mode = mode if mode in ("ja", "alt") else "ja"
    doc = _get_doc(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="変換データが見つかりません。もう一度PDFを変換してください。",
        )
    try:
        pdf_bytes = pdf_export.build_pdf(doc["data"], doc["result"]["pages"], mode=mode)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"PDF生成に失敗しました: {e}")

    fname = _download_filename(doc["result"].get("filename", "readable.pdf"), mode)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


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
