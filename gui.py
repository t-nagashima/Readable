#!/usr/bin/env python3
"""Readable GUI — 英語PDF論文を日本語PDFに変換するデスクトップアプリ。

コマンドプロンプト不要。ファイル/フォルダを選んでボタンを押すだけ。
PyInstaller で exe 化できます（build_exe.bat 参照）。
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# 共有ロジック（CLIと同じエンジン）を読み込む
if getattr(sys, "frozen", False):
    _BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
else:
    _BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(_BASE))
sys.path.insert(0, str(_BASE / "backend"))

import readable  # noqa: E402
import pdf_processor  # noqa: E402
import translator  # noqa: E402

# 画面表示と内部値の対応
MODE_LABELS = {"日本語のみ": "ja", "英日交互（対訳）": "alt", "両方": "both"}
ENGINE_LABELS = {"ローカルLLM (Ollama)": "ollama", "Google翻訳（無料・高速）": "google"}
OCR_LABELS = {"自動（スキャンを検出）": "auto", "常にOCR": "force", "OCRしない": "off"}


def open_folder(path: Path) -> None:
    """OSの標準ファイラで出力フォルダを開く。"""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


class ReadableApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Readable — 英語論文を日本語PDFに")
        root.geometry("720x620")
        root.minsize(640, 560)

        self.msg_queue: "queue.Queue[tuple]" = queue.Queue()
        self.worker: threading.Thread | None = None
        self.last_out_dir: Path | None = None

        self._build_ui()
        self._refresh_engine_state()
        self.root.after(100, self._drain_queue)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        r = 0
        ttk.Label(frm, text="入力（PDFファイル or フォルダ）").grid(row=r, column=0, sticky="w", **pad)
        self.input_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.input_var).grid(row=r, column=1, sticky="ew", **pad)
        btns = ttk.Frame(frm)
        btns.grid(row=r, column=2, sticky="e", **pad)
        ttk.Button(btns, text="ファイル", command=self._pick_file).pack(side="left")
        ttk.Button(btns, text="フォルダ", command=self._pick_folder).pack(side="left", padx=(4, 0))

        r += 1
        ttk.Label(frm, text="出力フォルダ（空=入力と同じ）").grid(row=r, column=0, sticky="w", **pad)
        self.output_var = tk.StringVar()
        ttk.Entry(frm, textvariable=self.output_var).grid(row=r, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="選択", command=self._pick_output).grid(row=r, column=2, sticky="e", **pad)

        r += 1
        ttk.Label(frm, text="出力形式").grid(row=r, column=0, sticky="w", **pad)
        self.mode_var = tk.StringVar(value="日本語のみ")
        ttk.Combobox(frm, textvariable=self.mode_var, values=list(MODE_LABELS),
                     state="readonly").grid(row=r, column=1, columnspan=2, sticky="ew", **pad)

        r += 1
        ttk.Label(frm, text="翻訳エンジン").grid(row=r, column=0, sticky="w", **pad)
        self.engine_var = tk.StringVar(value="ローカルLLM (Ollama)")
        eng = ttk.Combobox(frm, textvariable=self.engine_var, values=list(ENGINE_LABELS),
                           state="readonly")
        eng.grid(row=r, column=1, columnspan=2, sticky="ew", **pad)
        eng.bind("<<ComboboxSelected>>", lambda e: self._refresh_engine_state())

        r += 1
        ttk.Label(frm, text="モデル（Ollama）").grid(row=r, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar(value="qwen2.5")
        self.model_cb = ttk.Combobox(frm, textvariable=self.model_var, values=["qwen2.5"])
        self.model_cb.grid(row=r, column=1, columnspan=2, sticky="ew", **pad)

        r += 1
        ttk.Label(frm, text="OCR（スキャンPDF）").grid(row=r, column=0, sticky="w", **pad)
        self.ocr_var = tk.StringVar(value="自動（スキャンを検出）")
        ttk.Combobox(frm, textvariable=self.ocr_var, values=list(OCR_LABELS),
                     state="readonly").grid(row=r, column=1, columnspan=2, sticky="ew", **pad)

        r += 1
        opt = ttk.Frame(frm)
        opt.grid(row=r, column=0, columnspan=3, sticky="w", **pad)
        ttk.Label(opt, text="ページ数（0=全部）:").pack(side="left")
        self.pages_var = tk.StringVar(value="0")
        ttk.Spinbox(opt, from_=0, to=9999, width=6, textvariable=self.pages_var).pack(side="left", padx=(4, 16))
        self.recursive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="フォルダを再帰探索", variable=self.recursive_var).pack(side="left")

        r += 1
        self.status_var = tk.StringVar(value="")
        ttk.Label(frm, textvariable=self.status_var, foreground="#b45309").grid(
            row=r, column=0, columnspan=3, sticky="w", padx=10)

        r += 1
        self.run_btn = ttk.Button(frm, text="▶ 変換開始", command=self._start)
        self.run_btn.grid(row=r, column=0, sticky="w", **pad)
        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.grid(row=r, column=1, sticky="ew", **pad)
        self.open_btn = ttk.Button(frm, text="📂 出力を開く", command=self._open_output, state="disabled")
        self.open_btn.grid(row=r, column=2, sticky="e", **pad)

        r += 1
        frm.rowconfigure(r, weight=1)
        logf = ttk.Frame(frm)
        logf.grid(row=r, column=0, columnspan=3, sticky="nsew", padx=10, pady=(6, 0))
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.log = tk.Text(logf, height=10, wrap="word", state="disabled",
                           bg="#0f172a", fg="#e2e8f0", insertbackground="#e2e8f0")
        self.log.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(logf, command=self.log.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log.config(yscrollcommand=sb.set)

    # ------------------------------------------------------------- helpers
    def _pick_file(self) -> None:
        p = filedialog.askopenfilename(title="PDFを選択", filetypes=[("PDF", "*.pdf")])
        if p:
            self.input_var.set(p)

    def _pick_folder(self) -> None:
        p = filedialog.askdirectory(title="PDFを含むフォルダを選択")
        if p:
            self.input_var.set(p)

    def _pick_output(self) -> None:
        p = filedialog.askdirectory(title="出力先フォルダを選択")
        if p:
            self.output_var.set(p)

    def _open_output(self) -> None:
        if self.last_out_dir:
            open_folder(self.last_out_dir)

    def _log(self, msg: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _refresh_engine_state(self) -> None:
        """エンジン選択に応じてモデル欄の状態とOllama接続状況を更新する。"""
        engine = ENGINE_LABELS[self.engine_var.get()]
        if engine == "ollama":
            self.model_cb.config(state="normal")
            status = translator.ollama_status()
            if status.get("available"):
                models = status.get("models") or ["qwen2.5"]
                self.model_cb.config(values=models)
                if self.model_var.get() not in models:
                    self.model_var.set(models[0])
                self.status_var.set(f"✅ Ollama 接続OK — モデル {len(models)} 件")
            else:
                self.status_var.set(
                    "⚠️ Ollama に接続できません。setup を実行するか『ollama serve』を起動してください"
                )
        else:
            self.model_cb.config(state="disabled")
            self.status_var.set("")

    # --------------------------------------------------------------- run
    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        input_path = self.input_var.get().strip()
        if not input_path:
            messagebox.showwarning("入力なし", "PDFファイルかフォルダを選択してください。")
            return

        params = {
            "input": Path(input_path).expanduser(),
            "output": self.output_var.get().strip(),
            "mode": MODE_LABELS[self.mode_var.get()],
            "engine": ENGINE_LABELS[self.engine_var.get()],
            "model": self.model_var.get().strip() or None,
            "ocr": OCR_LABELS[self.ocr_var.get()],
            "pages": int(self.pages_var.get() or 0),
            "recursive": self.recursive_var.get(),
        }

        self.run_btn.config(state="disabled")
        self.open_btn.config(state="disabled")
        self.progress.config(value=0, maximum=100)
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

        self.worker = threading.Thread(target=self._worker, args=(params,), daemon=True)
        self.worker.start()

    def _worker(self, p: dict) -> None:
        q = self.msg_queue
        try:
            pdfs = readable.collect_pdfs(p["input"], p["recursive"])
        except SystemExit as e:
            q.put(("error", str(e)))
            q.put(("done", None))
            return

        # 出力先の決定
        if p["output"]:
            out_dir = Path(p["output"]).expanduser()
        elif p["input"].is_dir():
            out_dir = p["input"]
        else:
            out_dir = p["input"].parent
        out_dir.mkdir(parents=True, exist_ok=True)

        # Ollama の事前チェック
        if p["engine"] == "ollama":
            st = translator.ollama_status()
            if not st.get("available"):
                q.put(("error", "Ollama に接続できません。setup を実行するか『ollama serve』を起動してください。"))
                q.put(("done", None))
                return

        q.put(("log", f"対象 {len(pdfs)} 件 / エンジン: {p['engine']} / 出力: {out_dir}"))
        q.put(("maxfiles", len(pdfs)))

        ok = failed = 0
        for i, src in enumerate(pdfs, 1):
            q.put(("log", f"[{i}/{len(pdfs)}] {src.name} ..."))
            q.put(("file", (i - 1, len(pdfs))))
            try:
                written = readable.translate_pdf(
                    src, out_dir, p["mode"], p["engine"], p["model"], p["ocr"], p["pages"],
                    progress=lambda d, t, _i=i, _n=len(pdfs): q.put(("page", (_i, _n, d, t))),
                    log=lambda m: q.put(("log", m)),
                )
                for w in written:
                    q.put(("log", f"    ✓ {w.name}"))
                ok += 1
            except Exception as e:  # noqa: BLE001
                failed += 1
                q.put(("log", f"    ✕ 失敗: {e}"))
            q.put(("file", (i, len(pdfs))))

        q.put(("log", f"\n完了: 成功 {ok} 件 / 失敗 {failed} 件"))
        q.put(("finished", out_dir))
        q.put(("done", None))

    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "error":
                    messagebox.showerror("エラー", payload)
                elif kind == "maxfiles":
                    self.progress.config(value=0, maximum=max(1, payload) * 100)
                elif kind == "file":
                    i, n = payload
                    self.progress.config(value=i * 100)
                elif kind == "page":
                    fi, fn, d, t = payload
                    # ファイル単位の進捗 + ファイル内ページ進捗を合成
                    frac = (fi - 1 + (d / t if t else 1)) * 100
                    self.progress.config(value=frac)
                elif kind == "finished":
                    self.last_out_dir = payload
                    self.open_btn.config(state="normal")
                elif kind == "done":
                    self.run_btn.config(state="normal")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)


def main() -> int:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    ReadableApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
