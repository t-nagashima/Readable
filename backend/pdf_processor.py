"""PDF を解析し、ページ画像とテキストブロック（座標付き）を抽出する。

PyMuPDF (fitz) を使用。各ブロックの bbox は PDF のポイント座標で返し、
フロント側で表示倍率に合わせてスケールする。
"""

from __future__ import annotations

import base64
import re
import shutil

import fitz  # PyMuPDF

# ページレンダリングの解像度倍率（高いほど鮮明・重い）
RENDER_ZOOM = 2.0
# OCR 時の解像度
OCR_DPI = 200
# このアルファベット文字数未満のページは「スキャン画像」とみなし OCR 候補にする
SCANNED_TEXT_THRESHOLD = 20


def ocr_available() -> bool:
    """Tesseract が利用可能かどうか。"""
    return shutil.which("tesseract") is not None


def _looks_like_paragraph(text: str) -> bool:
    """翻訳対象にすべき本文ブロックかをざっくり判定する。"""
    t = text.strip()
    if len(t) < 2:
        return False
    # 数字・記号だけ（ページ番号や数式の断片など）は除外
    letters = sum(c.isalpha() for c in t)
    if letters < 2:
        return False
    return True


def _clean_text(text: str) -> str:
    """PDF 由来の不要な改行・ハイフネーションを整形する。"""
    # 行末ハイフンで分割された単語を連結 (e.g. "trans-\nlation" -> "translation")
    text = re.sub(r"-\n(\w)", r"\1", text)
    # 段落内の改行は空白に
    text = re.sub(r"\s*\n\s*", " ", text)
    return text.strip()


def _alpha_count(page) -> int:
    return sum(c.isalpha() for c in page.get_text("text"))


def _get_page_textpage(page, ocr_mode: str):
    """ページのテキスト抽出元 (textpage) と、OCRを使ったかを返す。

    ocr_mode: "auto"(本文が乏しければOCR) / "force"(常にOCR) / "off"(OCRしない)
    """
    use_ocr = False
    if ocr_mode == "force":
        use_ocr = True
    elif ocr_mode == "auto":
        use_ocr = _alpha_count(page) < SCANNED_TEXT_THRESHOLD

    if use_ocr and ocr_available():
        try:
            tp = page.get_textpage_ocr(language="eng", dpi=OCR_DPI, full=True)
            return tp, True
        except Exception:
            # OCR 失敗時は通常抽出にフォールバック
            return page.get_textpage(), False
    return page.get_textpage(), False


def _extract_blocks(page, pno: int, textpage) -> list[dict]:
    blocks_out: list[dict] = []
    page_dict = page.get_text("dict", textpage=textpage)
    bidx = 0
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # 0=テキスト, 1=画像
            continue
        lines = block.get("lines", [])
        sizes: list[float] = []
        for line in lines:
            for span in line.get("spans", []):
                sizes.append(span.get("size", 0))
        raw = "\n".join(
            "".join(s.get("text", "") for s in line.get("spans", []))
            for line in lines
        )
        text = _clean_text(raw)
        if not _looks_like_paragraph(text):
            continue
        bidx += 1
        x0, y0, x1, y1 = block["bbox"]
        avg_size = round(sum(sizes) / len(sizes), 1) if sizes else 0
        blocks_out.append(
            {
                "id": f"p{pno}b{bidx}",
                "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                "source": text,
                "size": avg_size,
            }
        )
    return blocks_out


def process_pdf(data: bytes, max_pages: int = 0, ocr: str = "auto") -> dict:
    """PDF バイト列を解析して、ページごとの画像とブロック情報を返す。

    ocr: "auto"(既定/必要時のみOCR) / "force"(常にOCR) / "off"(OCRしない)

    返り値:
        {
          "pages": [
            {
              "index": 0,
              "width": <pt>, "height": <pt>,
              "image": "data:image/png;base64,...",
              "ocr": <bool>,
              "blocks": [
                {"id": "p0b1", "bbox": [x0,y0,x1,y1],
                 "source": "...", "size": <平均フォントサイズ>}
              ]
            }
          ]
        }
    """
    doc = fitz.open(stream=data, filetype="pdf")
    pages_out = []
    mat = fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM)
    ocr_used_any = False

    page_count = doc.page_count
    if max_pages and max_pages > 0:
        page_count = min(page_count, max_pages)

    for pno in range(page_count):
        page = doc.load_page(pno)
        rect = page.rect

        # ページ画像（PNG → base64）
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")

        textpage, page_ocr = _get_page_textpage(page, ocr)
        ocr_used_any = ocr_used_any or page_ocr
        blocks_out = _extract_blocks(page, pno, textpage)

        pages_out.append(
            {
                "index": pno,
                "width": round(rect.width, 1),
                "height": round(rect.height, 1),
                "image": f"data:image/png;base64,{img_b64}",
                "ocr": page_ocr,
                "blocks": blocks_out,
            }
        )

    total = doc.page_count
    doc.close()
    return {
        "pages": pages_out,
        "total_pages": total,
        "rendered_pages": page_count,
        "ocr_used": ocr_used_any,
    }
