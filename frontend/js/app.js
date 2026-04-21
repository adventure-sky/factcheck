/* ── 設定 ────────────────────────────────────────────── */
const API_BASE = "http://localhost:8000";

/* ── 狀態 ────────────────────────────────────────────── */
let currentInputType = "text";
let selectedFile = null;
let selectedFileDataURL = null;

/* ── 輸入類型切換 ─────────────────────────────────────── */
function switchInputType(type, btn) {
  currentInputType = type;
  document.querySelectorAll(".input-tab").forEach(t => t.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("input-text").classList.toggle("hidden", type !== "text");
  document.getElementById("input-url").classList.toggle("hidden", type !== "url");
  document.getElementById("input-image").classList.toggle("hidden", type !== "image");
}

/* ── 圖片上傳 ─────────────────────────────────────────── */
function handleDragOver(e) {
  e.preventDefault();
  document.getElementById("upload-area").classList.add("dragover");
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById("upload-area").classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (file) previewFile(file);
}

function handleFileSelect(e) {
  const file = e.target.files[0];
  if (file) previewFile(file);
}

function previewFile(file) {
  selectedFile = file;
  const reader = new FileReader();
  reader.onload = (e) => {
    selectedFileDataURL = e.target.result;
    document.getElementById("preview-img").src = e.target.result;
    document.getElementById("file-name").textContent = file.name;
    document.getElementById("image-preview").classList.remove("hidden");
    document.getElementById("upload-area").classList.add("hidden");
    document.getElementById("clear-image-btn")?.classList.remove("hidden");
  };
  reader.readAsDataURL(file);
}

/* ── 查核提交 ─────────────────────────────────────────── */
async function submitCheck(mode) {
  if (currentInputType === "image") {
    await submitImageCheck(mode);
  } else {
    await submitTextCheck(mode);
  }
}

async function submitTextCheck(mode) {
  let content = "";
  if (currentInputType === "text") {
    content = document.getElementById("text-input").value.trim();
  } else {
    content = document.getElementById("url-input").value.trim();
  }

  if (!content) {
    showError(currentInputType === "text" ? "請輸入要查核的訊息內容。" : "請輸入要查核的網址。", "ERR_EMPTY_INPUT");
    return;
  }

  showLoading("正在查核中，請稍候...", "");

  try {
    // 平行查詢兩個模式，切換時零等待
    const [citizenRes, proRes] = await Promise.all([
      fetch(`${API_BASE}/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, mode: "citizen" }),
      }),
      fetch(`${API_BASE}/check`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, mode: "professional" }),
      }),
    ]);

    if (!citizenRes.ok) throw new Error(`HTTP ${citizenRes.status}`);
    if (!proRes.ok) throw new Error(`HTTP ${proRes.status}`);

    const citizenData = await citizenRes.json();
    const proData     = await proRes.json();

    sessionStorage.setItem("checkResult_citizen",      JSON.stringify({ ...citizenData, input: content }));
    sessionStorage.setItem("checkResult_professional", JSON.stringify({ ...proData,     input: content }));
    // backward compat：checkResult 指向所選模式
    sessionStorage.setItem("checkResult", JSON.stringify(
      mode === "citizen"
        ? { ...citizenData, input: content }
        : { ...proData,     input: content }
    ));

    if (mode === "citizen") {
      window.location.href = "result-citizen.html";
    } else {
      window.location.href = "result-professional.html";
    }
  } catch (err) {
    hideLoading();
    showError(`查核失敗：${err.message}\n請確認後端服務是否已啟動。`, "ERR_CHECK_FAILED");
  }
}

async function submitImageCheck(mode) {
  if (!selectedFile) {
    showError("請先選擇圖片再送出查核。", "ERR_NO_IMAGE");
    return;
  }

  showLoading("正在分析圖片...", "", true, selectedFileDataURL);

  const formData = new FormData();
  formData.append("image", selectedFile);
  formData.append("mode", mode);

  try {
    const res = await fetch(`${API_BASE}/check/image`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    sessionStorage.setItem("checkResult", JSON.stringify({
      ...data,
      input: selectedFile.name,
      inputType: "image",
      imageDataURL: selectedFileDataURL,
    }));

    if (mode === "citizen") {
      window.location.href = "result-citizen.html";
    } else {
      window.location.href = "result-professional.html";
    }
  } catch (err) {
    hideLoading();
    showError(`圖片分析失敗：${err.message}`, "ERR_IMAGE_ANALYSIS");
  }
}

/* ── Loading ─────────────────────────────────────────── */
const TEXT_LOADING_STEPS = [
  { tag: "[INIT]",  text: "正在啟動 Llama-3-70b 語言模型..." },
  { tag: "[FCK]",   text: "正在比對 Google Fact Check 外部資料庫..." },
  { tag: "[DB]",    text: "正在檢索 ChromaDB 向量資料庫（265,952 筆）..." },
  { tag: "[RAG]",   text: "正在進行語義相似度分析與 Reranking..." },
  { tag: "[FINAL]", text: "正在生成結構化情報報告..." },
];
const IMAGE_LOADING_STEPS = [
  { tag: "[SCAN]",   text: "正在讀取圖片像素特徵..." },
  { tag: "[AI]",     text: "正在呼叫 AI or Not 偵測引擎..." },
  { tag: "[VISION]", text: "Groq Vision 正在分析視覺異常..." },
  { tag: "[FINAL]",  text: "正在整合 AI 生成概率報告..." },
];

let _loadingTimer = null;
let _coordTimer = null;

function _randCoord() {
  const x = String(Math.floor(Math.random() * 4096)).padStart(4, "0");
  const y = String(Math.floor(Math.random() * 3072)).padStart(4, "0");
  const el = document.getElementById("scan-coords");
  if (el) el.textContent = `[X:${x} Y:${y}]`;
}

function _appendLogLine(containerId, tag, text, state = "done") {
  const container = document.getElementById(containerId);
  if (!container) return;
  const line = document.createElement("div");
  line.className = `log-line log-line--${state}`;
  line.innerHTML = `<span class="log-tag">${tag}</span><span>${text}</span>`;
  container.appendChild(line);
}

function showLoading(text, sub, isImage = false, imageDataURL = null) {
  const overlay = document.getElementById("loading-overlay");
  const imgMode  = document.getElementById("loading-image-mode");
  const textMode = document.getElementById("loading-text-mode");

  // 清空 log
  const logId = isImage ? "scan-log" : "text-log";
  const logEl = document.getElementById(logId);
  if (logEl) logEl.innerHTML = "";

  // 顯示對應 panel
  imgMode.classList.toggle("hidden", !isImage);
  textMode.classList.toggle("hidden", isImage);
  overlay.classList.remove("hidden");

  // 圖片模式：設定預覽圖 + 座標動畫
  if (isImage) {
    const img = document.getElementById("scan-img");
    if (img && imageDataURL) img.src = imageDataURL;
    if (_coordTimer) clearInterval(_coordTimer);
    _coordTimer = setInterval(_randCoord, 120);
  } else {
    const titleEl = document.getElementById("loading-text");
    if (titleEl) titleEl.textContent = text || "正在查核中...";
  }

  // 步驟 log 逐行出現
  const steps = isImage ? IMAGE_LOADING_STEPS : TEXT_LOADING_STEPS;
  let i = 0;
  if (_loadingTimer) clearInterval(_loadingTimer);
  _appendLogLine(logId, steps[0].tag, steps[0].text, "active");

  _loadingTimer = setInterval(() => {
    i++;
    if (i >= steps.length) { i = steps.length - 1; return; }
    // 把上一行改成 done
    const container = document.getElementById(logId);
    if (container) {
      const lines = container.querySelectorAll(".log-line");
      lines.forEach(l => { l.classList.remove("log-line--active"); l.classList.add("log-line--done"); });
    }
    _appendLogLine(logId, steps[i].tag, steps[i].text, "active");
  }, 2000);
}

function hideLoading() {
  if (_loadingTimer) { clearInterval(_loadingTimer); _loadingTimer = null; }
  if (_coordTimer)   { clearInterval(_coordTimer);   _coordTimer   = null; }
  document.getElementById("loading-overlay").classList.add("hidden");
}

function cancelLoading() {
  hideLoading();
  // 中止任何進行中的 fetch（若有 AbortController 可在此 abort）
  // 目前直接回到輸入狀態即可，頁面本身不跳轉
}

/* ── Error Modal ─────────────────────────────────────── */
function showError(message, code = "ERR_UNKNOWN") {
  document.getElementById("error-message").textContent = message;
  document.getElementById("error-code").textContent = code;
  document.getElementById("error-modal").classList.remove("hidden");
  document.getElementById("error-modal").style.display = "flex";
}

function hideError() {
  document.getElementById("error-modal").classList.add("hidden");
  document.getElementById("error-modal").style.display = "none";
}
