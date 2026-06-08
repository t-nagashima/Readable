// Readable フロントエンド
const $ = (sel) => document.querySelector(sel);

const uploadView = $("#upload-view");
const loadingView = $("#loading-view");
const resultView = $("#result-view");
const loadingText = $("#loading-text");
const dropzone = $("#dropzone");
const fileInput = $("#file-input");
const pagesEl = $("#pages");
const docTitle = $("#doc-title");

let currentData = null;
let currentMode = "overlay";
let currentDocId = null;
let ollamaInfo = { available: false, models: [] };

const engineSel = $("#engine");
const modelLabel = $("#model-label");
const modelSel = $("#model");
const ollamaStatusEl = $("#ollama-status");
const ocrStatusEl = $("#ocr-status");

// ---------- エンジン情報の取得 ----------
async function loadEngines() {
  try {
    const res = await fetch("/api/engines");
    const info = await res.json();
    ollamaInfo = info.ollama || { available: false, models: [] };
    if (info.default === "ollama" && ollamaInfo.available) {
      engineSel.value = "ollama";
    }
    if (!info.ocr_available) {
      ocrStatusEl.className = "ollama-status warn";
      ocrStatusEl.innerHTML =
        "⚠️ OCR (Tesseract) が未インストールです。スキャンPDFを変換するには " +
        "<code>tesseract-ocr</code> をインストールしてください。";
    }
  } catch {
    ollamaInfo = { available: false, models: [] };
  }
  updateEngineUI();
}

function updateEngineUI() {
  const isOllama = engineSel.value === "ollama";
  modelLabel.classList.toggle("hidden", !isOllama);

  if (!isOllama) {
    ollamaStatusEl.textContent = "";
    return;
  }

  if (ollamaInfo.available) {
    modelSel.innerHTML = "";
    const models = ollamaInfo.models.length ? ollamaInfo.models : ["qwen2.5"];
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      modelSel.appendChild(opt);
    }
    ollamaStatusEl.className = "ollama-status ok";
    ollamaStatusEl.textContent = `✅ Ollama 接続OK（${ollamaInfo.host}） — モデル ${models.length} 件`;
  } else {
    modelSel.innerHTML = '<option value="qwen2.5">qwen2.5</option>';
    ollamaStatusEl.className = "ollama-status warn";
    ollamaStatusEl.innerHTML =
      "⚠️ Ollama に接続できません。<br>" +
      "<code>ollama serve</code> を起動し <code>ollama pull qwen2.5</code> でモデルを取得してください。";
  }
}

engineSel.addEventListener("change", updateEngineUI);
loadEngines();

// ---------- 画面遷移 ----------
function show(view) {
  for (const v of [uploadView, loadingView, resultView]) v.classList.add("hidden");
  view.classList.remove("hidden");
}

// ---------- アップロード操作 ----------
dropzone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleFile(fileInput.files[0]);
});
["dragover", "dragenter"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag");
  })
);
["dragleave", "drop"].forEach((ev) =>
  dropzone.addEventListener(ev, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
  })
);
dropzone.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});

$("#back-btn").addEventListener("click", () => {
  fileInput.value = "";
  show(uploadView);
});

// ---------- 表示モード切替 ----------
document.querySelectorAll(".mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".mode-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
    render();
  });
});

// ---------- 変換リクエスト ----------
async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    alert("PDFファイルを選択してください。");
    return;
  }
  show(loadingView);
  loadingText.textContent = "PDFを解析・翻訳中…（ページ数によって数十秒かかります）";

  const engine = engineSel.value;
  const form = new FormData();
  form.append("file", file);
  form.append("target", "ja");
  form.append("max_pages", $("#max-pages").value);
  form.append("engine", engine);
  form.append("ocr", $("#ocr").value);
  if (engine === "ollama") form.append("model", modelSel.value || "qwen2.5");

  if (engine === "ollama") {
    loadingText.textContent =
      "ローカルLLM (Ollama) で翻訳中…（モデルやページ数により数分かかることがあります）";
  }

  try {
    const res = await fetch("/api/convert", { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "変換に失敗しました");
    }
    currentData = await res.json();
    currentDocId = currentData.doc_id || null;
    docTitle.textContent = currentData.filename || "";
    if (currentData.ocr_used) {
      docTitle.textContent += "（OCR適用）";
    }
    show(resultView);
    render();
  } catch (e) {
    show(uploadView);
    showError(e.message);
  }
}

// ---------- ダウンロード ----------
$("#download-btn").addEventListener("click", () => {
  if (!currentDocId) {
    alert("ダウンロードできるデータがありません。");
    return;
  }
  const mode = $("#dl-mode").value;
  const url = `/api/download?doc_id=${encodeURIComponent(currentDocId)}&mode=${mode}`;
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
});

function showError(msg) {
  const box = document.createElement("div");
  box.className = "error-box";
  box.textContent = "⚠️ " + msg;
  uploadView.prepend(box);
  setTimeout(() => box.remove(), 6000);
}

// ---------- レンダリング ----------
function render() {
  if (!currentData) return;
  pagesEl.innerHTML = "";
  for (const page of currentData.pages) {
    pagesEl.appendChild(renderPage(page));
  }
  if (currentData.rendered_pages < currentData.total_pages) {
    const note = document.createElement("p");
    note.className = "page-label";
    note.textContent = `全 ${currentData.total_pages} ページ中 ${currentData.rendered_pages} ページを表示`;
    pagesEl.appendChild(note);
  }
}

function renderPage(page) {
  const wrap = document.createElement("div");
  wrap.style.width = "100%";
  wrap.style.maxWidth = "850px";

  const label = document.createElement("div");
  label.className = "page-label";
  label.textContent = `p. ${page.index + 1}`;

  let body;
  if (currentMode === "overlay") body = renderOverlay(page);
  else if (currentMode === "side") body = renderSide(page);
  else body = renderOriginal(page);

  wrap.appendChild(body);
  wrap.appendChild(label);
  return wrap;
}

function renderOverlay(page) {
  const card = document.createElement("div");
  card.className = "page-wrap";
  const canvas = document.createElement("div");
  canvas.className = "page-canvas";

  const img = document.createElement("img");
  img.src = page.image;
  canvas.appendChild(img);

  // bbox は PDF ポイント座標。画像幅に対する % で配置する。
  for (const b of page.blocks) {
    if (!b.target) continue;
    const [x0, y0, x1, y1] = b.bbox;
    const div = document.createElement("div");
    div.className = "ov-block";
    div.style.left = pct(x0, page.width);
    div.style.top = pct(y0, page.height);
    div.style.width = pct(x1 - x0, page.width);
    div.style.height = pct(y1 - y0, page.height);

    const span = document.createElement("span");
    span.textContent = b.target;
    // ブロックの高さに合わせてフォントサイズと行数を推定
    const fs = Math.max(7, Math.min(13, (b.size || 10) * 0.92));
    span.style.fontSize = fs + "px";
    const lines = Math.max(1, Math.floor((y1 - y0) / (fs * 1.25)));
    span.style.webkitLineClamp = String(lines);
    div.appendChild(span);
    div.title = b.source;
    canvas.appendChild(div);
  }
  card.appendChild(canvas);
  return card;
}

function renderSide(page) {
  const grid = document.createElement("div");
  grid.className = "side-page";

  const img = document.createElement("img");
  img.src = page.image;

  const text = document.createElement("div");
  text.className = "side-text";
  for (const b of page.blocks) {
    if (!b.target) continue;
    const blk = document.createElement("div");
    blk.className = "blk";
    const ja = document.createElement("div");
    ja.className = "ja";
    ja.textContent = b.target;
    const en = document.createElement("div");
    en.className = "en";
    en.textContent = b.source;
    blk.appendChild(ja);
    blk.appendChild(en);
    text.appendChild(blk);
  }
  grid.appendChild(img);
  grid.appendChild(text);
  return grid;
}

function renderOriginal(page) {
  const card = document.createElement("div");
  card.className = "page-wrap original-page";
  const img = document.createElement("img");
  img.src = page.image;
  card.appendChild(img);
  return card;
}

function pct(v, total) {
  return (100 * v) / total + "%";
}
