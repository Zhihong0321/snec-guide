const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const statusEl = document.getElementById("status");
const modelSelect = document.getElementById("modelSelect");
const webSearchToggle = document.getElementById("webSearchToggle");

const MODEL_STORAGE_KEY = "snec_chat_model";
const WEB_SEARCH_STORAGE_KEY = "snec_web_search";

/** @type {{role: string, content: string}[]} */
let history = [];
/** @type {string} */
let selectedModel = "";

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

/** Whitelist: exhibitor links + floor plan images in assistant messages */
function linkifyAssistantContent(htmlEscaped) {
  let out = htmlEscaped.replace(
    /!\[([^\]]*)\]\((\/floor_plans\/[^)\s]+)\)/gi,
    (_m, alt, path) =>
      `<a href="${path}" target="_blank" rel="noopener" class="floor-plan-link">` +
      `<img src="${path}" alt="${alt}" class="floor-plan-img" loading="lazy" /></a>`,
  );
  out = out.replace(
    /\[([^\]]+)\]\(\/exhibitor\/(\d+)\)/g,
    (_m, label, id) => `<a href="/exhibitor/${id}">${label}</a>`,
  );
  out = out.replace(
    /(?<!href=")(?<!\>)\/exhibitor\/(\d+)\b/g,
    (_m, id) => `<a href="/exhibitor/${id}">/exhibitor/${id}</a>`,
  );
  out = out.replace(
    /(?<!href=")(?<!\>)(?<!\]\()(\/floor_plans\/[^\s<]+\.(?:jpg|jpeg|png|webp))/gi,
    (_m, path) => `<a href="${path}" target="_blank" rel="noopener">${path}</a>`,
  );
  return out;
}

function formatAssistantHtml(raw) {
  return linkifyAssistantContent(escapeHtml(raw));
}

function appendMessage(role, content, extraClass = "") {
  const el = document.createElement("div");
  el.className = `msg ${role} ${extraClass}`.trim();
  if (role === "assistant") {
    el.innerHTML = formatAssistantHtml(content);
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

function populateModels(data) {
  const models = data.models || [];
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
}

function getSelectedModel() {
  return modelSelect.value || selectedModel;
}

modelSelect.addEventListener("change", () => {
  selectedModel = modelSelect.value;
  localStorage.setItem(MODEL_STORAGE_KEY, selectedModel);
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
  if (!text) return;

  input.value = "";
  input.style.height = "auto";
  sendBtn.disabled = true;

  appendMessage("user", text);
  history.push({ role: "user", content: text });

  const assistantEl = appendMessage("assistant", "", "typing");

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
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
