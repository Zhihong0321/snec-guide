const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const statusEl = document.getElementById("status");
const modelSelect = document.getElementById("modelSelect");
const webSearchToggle = document.getElementById("webSearchToggle");
const imageInput = document.getElementById("imageInput");
const attachBtn = document.getElementById("attachBtn");
const imagePreview = document.getElementById("imagePreview");

const MODEL_STORAGE_KEY = "snec_chat_model";
const WEB_SEARCH_STORAGE_KEY = "snec_web_search";
const MAX_IMAGE_DIM = 1920;
const MAX_IMAGES = 4;

/** @type {{role: string, content: string, images?: string[]}[]} */
let history = [];
/** @type {string} */
let selectedModel = "";
/** @type {{id: string, supports_images?: boolean, available?: boolean}[]} */
let modelCatalog = [];
/** @type {string[]} */
let pendingImages = [];

const SUGGESTIONS = [
  "Where is LONGi booth?",
  "Show floor plan for hall 8.2H",
  "Metro to NECC from Pudong",
  "NECC venue overview map",
];

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Escape a value for use inside a double-quoted HTML attribute. */
function escapeAttr(s) {
  return escapeHtml(String(s)).replace(/'/g, "&#39;");
}

/** Human-readable label from a floor-plan path, e.g. "Hall 5.2H". */
function prettyPlanName(path) {
  const file = path.split("/").pop().replace(/\.(jpg|jpeg|png|webp)$/i, "");
  if (/overview/i.test(file)) return "NECC venue overview";
  if (/plaza/i.test(file)) return "Central plaza";
  const hall = file.match(/^(\d+(?:\.\d+)?[A-Za-z]?)$/);
  if (hall) return `Hall ${hall[1]}`;
  return file.replace(/[_-]+/g, " ");
}

/** Professional, self-contained floor-plan card with a graceful broken-image
 *  fallback (no ugly broken-image icon) and a tap-to-enlarge affordance. */
function floorPlanFigure(path, alt) {
  const safe = escapeAttr(path);
  const caption = (alt && alt.trim()) || prettyPlanName(path);
  const cap = escapeHtml(caption);
  return (
    `<figure class="plan">` +
    `<a href="${safe}" target="_blank" rel="noopener" class="plan-link">` +
    `<img src="${safe}" alt="${escapeAttr(caption)}" class="plan-img" loading="lazy" ` +
    `onerror="this.closest('.plan').classList.add('plan-broken')" ` +
    `onload="this.closest('.plan').classList.remove('plan-broken')" />` +
    `<span class="plan-fallback">📍 Map image unavailable — tap to open</span>` +
    `<span class="plan-zoom">⤢ Tap to enlarge</span>` +
    `</a>` +
    `<figcaption class="plan-cap">📐 Floor plan · ${cap}</figcaption>` +
    `</figure>`
  );
}

/** Render assistant text safely. Generated HTML is stashed behind sentinel
 *  tokens BEFORE escaping, so no rule can ever re-scan another rule's output
 *  (the bug that mangled <img src> attributes into broken images). */
function formatAssistantHtml(raw) {
  const tokens = [];
  const stash = (html) => `\x00${tokens.push(html) - 1}\x00`;

  // Tight, injection-safe path charset.
  const PLAN = "\\/floor_plans\\/[A-Za-z0-9._-]+\\.(?:jpg|jpeg|png|webp)";

  let s = raw;

  // 1) Markdown floor-plan image: ![alt](/floor_plans/x.jpg)
  s = s.replace(
    new RegExp(`!\\[([^\\]]*)\\]\\((${PLAN})\\)`, "gi"),
    (_m, alt, path) => stash(floorPlanFigure(path, alt)),
  );
  // 2) Raw <img ... src="/floor_plans/x.jpg" ...> the model sometimes emits
  s = s.replace(
    new RegExp(`<img\\b[^>]*?\\bsrc=["']?(${PLAN})["']?[^>]*?>`, "gi"),
    (_m, path) => stash(floorPlanFigure(path, "")),
  );
  // 3) Markdown exhibitor link: [label](/exhibitor/123)
  s = s.replace(
    /\[([^\]]+)\]\(\/exhibitor\/(\d+)\)/g,
    (_m, label, id) => stash(`<a href="/exhibitor/${id}">${escapeHtml(label)}</a>`),
  );
  // 4) Bare floor-plan path -> link
  s = s.replace(
    new RegExp(PLAN, "gi"),
    (m) => stash(`<a href="${escapeAttr(m)}" target="_blank" rel="noopener">${escapeHtml(m)}</a>`),
  );
  // 5) Bare exhibitor path -> link
  s = s.replace(
    /\/exhibitor\/(\d+)\b/g,
    (m, id) => stash(`<a href="/exhibitor/${id}">${escapeHtml(m)}</a>`),
  );

  // Escape everything the model produced, then apply light markdown.
  s = escapeHtml(s)
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");

  // Restore the trusted, pre-built components.
  return s.replace(/\x00(\d+)\x00/g, (_m, i) => tokens[Number(i)]);
}

function appendMessage(role, content, extraClass = "", images = []) {
  const el = document.createElement("div");
  el.className = `msg ${role} ${extraClass}`.trim();
  if (role === "assistant") {
    el.innerHTML = formatAssistantHtml(content);
  } else if (images.length) {
    if (content) {
      const text = document.createElement("div");
      text.className = "msg-text";
      text.textContent = content;
      el.appendChild(text);
    }
    const row = document.createElement("div");
    row.className = "msg-images";
    for (const src of images) {
      const img = document.createElement("img");
      img.src = src;
      img.alt = "Attached image";
      img.className = "msg-user-img";
      img.loading = "lazy";
      row.appendChild(img);
    }
    el.appendChild(row);
  } else {
    el.textContent = content;
  }
  chat.appendChild(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}

function showWelcome() {
  const el = document.createElement("div");
  el.className = "msg welcome";
  el.innerHTML = `
    <strong>Ask anything about SNEC PV+ 2026</strong>
    Exhibitors, halls, metro, products, and visit planning — grounded in your database.
    <div class="suggestions"></div>
  `;
  const box = el.querySelector(".suggestions");
  SUGGESTIONS.forEach((text) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = text;
    btn.addEventListener("click", () => {
      input.value = text;
      input.focus();
      form.requestSubmit();
    });
    box.appendChild(btn);
  });
  chat.appendChild(el);
}

function selectedModelSupportsImages() {
  const m = modelCatalog.find((x) => x.id === getSelectedModel());
  return Boolean(m?.supports_images);
}

function updateAttachUi() {
  const on = selectedModelSupportsImages();
  attachBtn.hidden = !on;
  if (!on) {
    pendingImages = [];
    renderImagePreview();
    imageInput.value = "";
  }
}

function loadImageFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read image."));
    };
    img.src = url;
  });
}

function resizeImageToDataUrl(img) {
  let { width, height } = img;
  if (width > MAX_IMAGE_DIM || height > MAX_IMAGE_DIM) {
    const scale = Math.min(MAX_IMAGE_DIM / width, MAX_IMAGE_DIM / height);
    width = Math.max(1, Math.round(width * scale));
    height = Math.max(1, Math.round(height * scale));
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported.");
  ctx.drawImage(img, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.85);
}

async function preprocessImageFile(file) {
  const img = await loadImageFile(file);
  return resizeImageToDataUrl(img);
}

function renderImagePreview() {
  imagePreview.innerHTML = "";
  if (!pendingImages.length) {
    imagePreview.hidden = true;
    return;
  }
  imagePreview.hidden = false;
  pendingImages.forEach((src, index) => {
    const wrap = document.createElement("div");
    wrap.className = "image-preview-item";
    const thumb = document.createElement("img");
    thumb.src = src;
    thumb.alt = `Attachment ${index + 1}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "image-preview-remove";
    remove.setAttribute("aria-label", "Remove image");
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      pendingImages.splice(index, 1);
      renderImagePreview();
    });
    wrap.appendChild(thumb);
    wrap.appendChild(remove);
    imagePreview.appendChild(wrap);
  });
}

async function addImageFiles(fileList) {
  if (!selectedModelSupportsImages()) return;
  const files = Array.from(fileList || []).filter((f) => f.type.startsWith("image/"));
  if (!files.length) return;
  const room = MAX_IMAGES - pendingImages.length;
  if (room <= 0) {
    statusEl.textContent = `Max ${MAX_IMAGES} images`;
    statusEl.className = "status warn";
    return;
  }
  for (const file of files.slice(0, room)) {
    try {
      pendingImages.push(await preprocessImageFile(file));
    } catch {
      statusEl.textContent = "Image failed";
      statusEl.className = "status warn";
    }
  }
  renderImagePreview();
}

function populateModels(data) {
  const models = data.models || [];
  modelCatalog = models;
  const saved = localStorage.getItem(MODEL_STORAGE_KEY);
  modelSelect.innerHTML = "";
  for (const m of models) {
    const opt = document.createElement("option");
    opt.value = m.id;
    opt.textContent = m.label;
    if (!m.available) {
      opt.disabled = true;
      opt.textContent += " (no API key)";
    }
    modelSelect.appendChild(opt);
  }
  const pick =
    models.find((m) => m.id === saved && m.available)?.id ||
    models.find((m) => m.available)?.id ||
    data.default_model ||
    models[0]?.id ||
    "";
  selectedModel = pick;
  if (pick) modelSelect.value = pick;
  updateAttachUi();
}

function getSelectedModel() {
  return modelSelect.value || selectedModel;
}

modelSelect.addEventListener("change", () => {
  selectedModel = modelSelect.value;
  localStorage.setItem(MODEL_STORAGE_KEY, selectedModel);
  updateAttachUi();
});

attachBtn.addEventListener("click", () => imageInput.click());
imageInput.addEventListener("change", () => {
  addImageFiles(imageInput.files);
  imageInput.value = "";
});

function initWebSearchToggle(data) {
  const ws = data.web_search || {};
  const canUse = ws.server_enabled && ws.engine_ready;
  const saved = localStorage.getItem(WEB_SEARCH_STORAGE_KEY);
  const defaultOn = ws.default_on !== false;
  webSearchToggle.checked = saved === null ? defaultOn : saved === "1";
  webSearchToggle.disabled = !canUse;
  if (!ws.server_enabled) {
    webSearchToggle.title = "Disabled on server (ENABLE_WEB_SEARCH=false)";
  } else if (!ws.engine_ready) {
    webSearchToggle.title = "Unavailable — install ddgs package on server";
  } else {
    webSearchToggle.title = "Fetch DuckDuckGo snippets before each answer";
  }
}

function getWebSearchEnabled() {
  return webSearchToggle.checked;
}

webSearchToggle.addEventListener("change", () => {
  localStorage.setItem(WEB_SEARCH_STORAGE_KEY, webSearchToggle.checked ? "1" : "0");
});

async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    populateModels(data);
    initWebSearchToggle(data);
    const anyModel = (data.models || []).some((m) => m.available);
    if (anyModel && data.database_configured) {
      statusEl.textContent = "Ready";
      statusEl.className = "status ok";
    } else if (anyModel) {
      statusEl.textContent = "No DB";
      statusEl.className = "status warn";
    } else {
      statusEl.textContent = "No API key";
      statusEl.className = "status warn";
    }
  } catch {
    statusEl.textContent = "Offline";
    statusEl.className = "status warn";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  const images = pendingImages.slice();
  if (!text && !images.length) return;

  input.value = "";
  input.style.height = "auto";
  pendingImages = [];
  renderImagePreview();
  sendBtn.disabled = true;

  appendMessage("user", text, "", images);
  const userTurn = { role: "user", content: text };
  if (images.length) userTurn.images = images;
  history.push(userTurn);

  const assistantEl = appendMessage("assistant", "", "typing");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        images,
        history: history.slice(0, -1),
        model: getSelectedModel(),
        web_search: getWebSearchEnabled(),
      }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let full = "";

    assistantEl.classList.remove("typing");

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      full += decoder.decode(value, { stream: true });
      assistantEl.innerHTML = formatAssistantHtml(full);
      chat.scrollTop = chat.scrollHeight;
    }

    history.push({ role: "assistant", content: full });
  } catch (err) {
    assistantEl.classList.remove("typing");
    assistantEl.innerHTML = formatAssistantHtml(`Could not reach the assistant. ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
});

input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

snecOnRegistered(() => {
  showWelcome();
  checkHealth();
});
