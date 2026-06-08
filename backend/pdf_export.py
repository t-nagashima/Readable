"""翻訳結果から日本語PDFを生成する。

2つのモード:
  - "ja"  : 日本語のみ（原文ページのレイアウト上で英文を日本語に置換）
  - "alt" : 英文ページと日本語ページを交互に並べる（対訳冊子）

原文の図表・レイアウトを保つため、元PDFのページを複製し、翻訳した
テキストブロックの位置を白で塗りつぶして日本語を流し込む。
日本語の描画には PyMuPDF 内蔵の CJK フォント "japan" を使う。
"""

from __future__ import annotations

import fitz  # PyMuPDF

JP_FONT = "japan"  # PyMuPDF 内蔵の日本語フォント
MIN_FONT = 5.0
MAX_FONT = 12.0


def _fit_text(page, rect: fitz.Rect, text: str, start_size: float) -> None:
    """rect 内に収まるようフォントサイズを縮小しながら日本語を描画する。"""
    size = max(MIN_FONT, min(MAX_FONT, start_size))
    while size >= MIN_FONT:
        # 元の英文を隠すため毎回白で塗りつぶしてから描画
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), width=0, overlay=True)
        leftover = page.insert_textbox(
            rect,
            text,
            fontname=JP_FONT,
            fontsize=size,
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
            overlay=True,
        )
        if leftover >= 0:  # 収まった
            return
        size -= 0.5
    # 最小サイズでも溢れる場合はクリップされた状態で確定（最後の描画が残る）


def _render_japanese_page(page, blocks: list[dict]) -> None:
    """複製済みページ上の英文ブロックを日本語に置き換える。"""
    for b in blocks:
        target = (b.get("target") or "").strip()
        if not target:
            continue
        x0, y0, x1, y1 = b["bbox"]
        rect = fitz.Rect(x0, y0, x1, y1)
        if rect.is_empty or rect.width < 4 or rect.height < 4:
            continue
        start = b.get("size") or 10
        _fit_text(page, rect, target, start)


def build_pdf(data: bytes, pages: list[dict], mode: str = "ja") -> bytes:
    """翻訳済みデータから PDF バイト列を生成する。

    data : 元PDFのバイト列
    pages: process_pdf の "pages"（各ブロックに "target" が入っている前提）
    mode : "ja"（日本語のみ）/ "alt"（英日交互）
    """
    src = fitz.open(stream=data, filetype="pdf")
    out = fitz.open()

    for page in pages:
        idx = page["index"]

        if mode == "alt":
            # 1) 英文ページ（原文をそのまま複製）
            out.insert_pdf(src, from_page=idx, to_page=idx)

        # 2) 日本語ページ（複製してから置換）
        out.insert_pdf(src, from_page=idx, to_page=idx)
        jp_page = out[-1]
        _render_japanese_page(jp_page, page.get("blocks", []))

    pdf_bytes = out.tobytes(garbage=3, deflate=True)
    out.close()
    src.close()
    return pdf_bytes
