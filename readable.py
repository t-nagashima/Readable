#!/usr/bin/env python3
"""Readable CLI — 英語PDF論文を日本語PDFに変換するコマンドラインツール。

ブラウザ不要。1ファイル指定でも、フォルダまるごと一括でも変換できる。

使い方:
    # 1ファイルを日本語PDFに変換（Ollama）
    python readable.py paper.pdf

    # フォルダ内のPDFをまとめて変換し、out/ に個別出力
    python readable.py ./papers -o ./out

    # 英日交互（対訳）でも同時に出力
    python readable.py paper.pdf --mode both

    # Google翻訳（無料・キー不要）を使う
    python readable.py paper.pdf --engine google

主なオプション:
    --mode {ja,alt,both}   ja=日本語のみ(既定) / alt=英日交互 / both=両方
    --engine {ollama,google}  既定: ollama
    --model NAME           Ollama のモデル名（既定: qwen2.5）
    --ocr {auto,force,off} スキャンPDFのOCR（既定: auto）
    -o, --output DIR       出力先フォルダ（既定: 入力と同じ場所）
    -r, --recursive        フォルダを再帰的に探索
    --pages N              先頭 N ページのみ（既定: 0=全部）
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Windows の cmd 等でも日本語・記号を安全に出力する（cp932 でのクラッシュ回避）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# backend/ のモジュールを import できるようにする。
# PyInstaller で exe 化した場合は同梱データ(_MEIPASS)から読み込む。
if getattr(sys, "frozen", False):
    _BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
else:
    _BASE = Path(__file__).resolve().parent
_BACKEND = _BASE / "backend"
sys.path.insert(0, str(_BACKEND))

import pdf_export  # noqa: E402
import pdf_processor  # noqa: E402
import translator  # noqa: E402


def _eprint(*args) -> None:
    # windowed な exe では sys.stderr が None になり得るため安全化
    try:
        print(*args, file=sys.stderr, flush=True)
    except Exception:
        pass


def collect_pdfs(input_path: Path, recursive: bool) -> list[Path]:
    """入力（ファイル/フォルダ）から対象PDFの一覧を作る。"""
    if input_path.is_file():
        if input_path.suffix.lower() != ".pdf":
            raise SystemExit(f"PDFファイルではありません: {input_path}")
        return [input_path]
    if input_path.is_dir():
        pattern = "**/*.pdf" if recursive else "*.pdf"
        pdfs = sorted(p for p in input_path.glob(pattern) if p.is_file())
        if not pdfs:
            raise SystemExit(f"PDFが見つかりません: {input_path}")
        return pdfs
    raise SystemExit(f"入力が見つかりません: {input_path}")


def output_paths(src: Path, out_dir: Path, mode: str) -> dict[str, Path]:
    """生成モードごとの出力ファイルパスを決める。"""
    stem = src.stem
    paths: dict[str, Path] = {}
    if mode in ("ja", "both"):
        paths["ja"] = out_dir / f"{stem}_ja.pdf"
    if mode in ("alt", "both"):
        paths["alt"] = out_dir / f"{stem}_bilingual.pdf"
    return paths


def translate_pdf(
    src: Path,
    out_dir: Path,
    mode: str,
    engine: str,
    model: str | None,
    ocr: str,
    pages: int,
    progress=None,
    log=None,
) -> list[Path]:
    """1つのPDFを変換し、生成したファイルパスの一覧を返す。

    progress: progress(done_pages, total_pages) を各ページ翻訳後に呼ぶ（任意）
    log:      log(message:str) で進捗メッセージを通知（任意。既定は標準エラー）
    """
    say = log or _eprint
    data = src.read_bytes()

    # 解析（CLIではページ画像は不要なので生成しない）
    result = pdf_processor.process_pdf(
        data, max_pages=pages, ocr=ocr, render_images=False
    )

    if result.get("ocr_used"):
        say("    （スキャンを検出: OCRを適用しました）")

    # 翻訳（ページごとにブロックをまとめて）
    total = len(result["pages"])
    for i, page in enumerate(result["pages"], 1):
        sources = [b["source"] for b in page["blocks"]]
        if sources:
            translations = translator.translate_texts(
                sources, target="ja", backend_name=engine, model=model
            )
            for b, tr in zip(page["blocks"], translations):
                b["target"] = tr
        if progress:
            progress(i, total)

    # PDF 生成
    written: list[Path] = []
    for m, path in output_paths(src, out_dir, mode).items():
        pdf_bytes = pdf_export.build_pdf(data, result["pages"], mode=m)
        path.write_bytes(pdf_bytes)
        written.append(path)
    return written


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="readable",
        description="英語PDF論文を日本語PDFに変換（1ファイル/フォルダ一括）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", help="PDFファイル、またはPDFを含むフォルダ")
    p.add_argument("-o", "--output", help="出力先フォルダ（既定: 入力と同じ場所）")
    p.add_argument(
        "--mode",
        choices=["ja", "alt", "both"],
        default="ja",
        help="ja=日本語のみ(既定) / alt=英日交互 / both=両方",
    )
    p.add_argument(
        "--engine",
        choices=["ollama", "google"],
        default="ollama",
        help="翻訳エンジン（既定: ollama）",
    )
    p.add_argument("--model", default=None, help="Ollamaのモデル名（既定: qwen2.5）")
    p.add_argument(
        "--ocr",
        choices=["auto", "force", "off"],
        default="auto",
        help="スキャンPDFのOCR（既定: auto）",
    )
    p.add_argument("--pages", type=int, default=0, help="先頭Nページのみ（既定: 0=全部）")
    p.add_argument(
        "-r", "--recursive", action="store_true", help="フォルダを再帰的に探索"
    )
    return p.parse_args(argv)


def preflight(engine: str, model: str | None, ocr: str) -> None:
    """実行前の環境チェック。問題があれば分かりやすく終了する。"""
    if engine == "ollama":
        status = translator.ollama_status()
        if not status.get("available"):
            raise SystemExit(
                "✕ Ollama に接続できません（"
                f"{status.get('host')}）。\n"
                "  まず環境構築スクリプトを実行してください:\n"
                "      ./setup.sh\n"
                "  もしくは Ollama を起動してください: ollama serve\n"
                "  Google翻訳で実行する場合は --engine google を指定してください。"
            )
        want = model or "qwen2.5"
        models = status.get("models", [])
        # "qwen2.5" は "qwen2.5:latest" として現れることがある
        if models and not any(m == want or m.split(":")[0] == want for m in models):
            _eprint(
                f"⚠ モデル '{want}' が見つかりません。インストール済み: {', '.join(models) or 'なし'}\n"
                f"  取得するには: ollama pull {want}"
            )
    if ocr in ("auto", "force") and not pdf_processor.ocr_available():
        _eprint(
            "⚠ Tesseract(OCR) が未インストールです。スキャンPDFは翻訳できません"
            "（テキスト層のあるPDFは問題ありません）。"
        )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    input_path = Path(args.input).expanduser().resolve()
    pdfs = collect_pdfs(input_path, args.recursive)

    # 出力先
    if args.output:
        out_dir = Path(args.output).expanduser().resolve()
    elif input_path.is_dir():
        out_dir = input_path
    else:
        out_dir = input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    preflight(args.engine, args.model, args.ocr)

    print(f"対象 {len(pdfs)} 件 / エンジン: {args.engine}"
          + (f" ({args.model or 'qwen2.5'})" if args.engine == "ollama" else "")
          + f" / モード: {args.mode}")
    print(f"出力先: {out_dir}\n")

    ok, failed = 0, 0
    t0 = time.time()
    for i, src in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {src.name} ...", flush=True)
        try:
            written = translate_pdf(
                src, out_dir, args.mode, args.engine, args.model, args.ocr, args.pages
            )
            for w in written:
                print(f"    ✓ {w}")
            ok += 1
        except KeyboardInterrupt:
            _eprint("\n中断しました。")
            return 130
        except Exception as e:  # noqa: BLE001
            failed += 1
            _eprint(f"    ✕ 失敗: {e}")

    dt = time.time() - t0
    print(f"\n完了: 成功 {ok} 件 / 失敗 {failed} 件（{dt:.1f}秒）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
