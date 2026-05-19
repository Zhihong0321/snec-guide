const $ = (id) => document.getElementById(id);

let currentExhibitorId = null;
let openedFromBrowse = false;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    credentials: "include",
    headers: opts.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res.text();
}

async function refreshMe() {
  const me = await api("/api/me");
  $("displayName").value = me.display_name || "";
  $("userMeta").textContent = `Cookie user id: ${me.user_id.slice(0, 8)}… (stored in HttpOnly cookie)`;
  return me;
}

function pathExhibitorId() {
  const m = window.location.pathname.match(/^\/exhibitor\/(\d+)\/?$/);
  return m ? parseInt(m[1], 10) : NaN;
}

function qsId() {
  const p = new URLSearchParams(window.location.search);
  const v = p.get("id");
  return v ? parseInt(v, 10) : NaN;
}

function initialExhibitorId() {
  const fromPath = pathExhibitorId();
  if (!Number.isNaN(fromPath)) return fromPath;
  return qsId();
}

function setUrlId(id) {
  window.history.replaceState({}, "", `/exhibitor/${id}`);
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function renderExhibitor(data) {
  const ex = data.exhibitor;
  currentExhibitorId = ex.id;
  $("detailSection").classList.remove("hidden");
  $("exTitle").textContent = ex.company_name_cn;
  const booth = ex.booth_display || [ex.hall, ex.booth].filter(Boolean).join(" ") || "Booth TBD";
  $("exMeta").textContent = [booth, ex.company_name_en].filter(Boolean).join(" · ");

  const nl = $("notesList");
  nl.innerHTML = "";
  for (const n of data.notes) {
    const li = document.createElement("li");
    li.className = "note-item";
    li.innerHTML = `<span class="note-meta">${esc(n.display_author)} · ${esc(String(n.created_at).slice(0, 19))}</span><div class="note-body">${esc(n.note_detail)}</div>`;
    nl.appendChild(li);
  }

  const ig = $("imageGrid");
  ig.innerHTML = "";
  for (const im of data.images) {
    const url = im.image_url || im.image_path;
    const card = document.createElement("div");
    card.className = "image-card";
    card.innerHTML = `
      <img src="${esc(url)}" alt="" loading="lazy" />
      <div class="image-cap">${esc(im.caption || "")}</div>
      <div class="image-meta">${esc(im.uploader_name || "—")}</div>
    `;
    ig.appendChild(card);
  }
}

async function loadExhibitor(id) {
  const data = await api(`/api/exhibitor/${id}`);
  renderExhibitor(data);
  setUrlId(id);
}

async function runSearch() {
  const q = $("searchQ").value.trim();
  if (!q) return;
  const { results } = await api(`/api/exhibitors/search?q=${encodeURIComponent(q)}`);
  const ul = $("searchResults");
  ul.innerHTML = "";
  for (const r of results) {
    const li = document.createElement("li");
    const booth = r.booth_display || [r.hall, r.booth].filter(Boolean).join(" ") || "TBD";
    li.innerHTML = `<button type="button" class="link-btn" data-id="${r.id}"><strong>${esc(r.company_name_cn)}</strong> <span class="muted">${esc(booth)}</span></button>`;
    ul.appendChild(li);
  }
  ul.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", () => {
      openedFromBrowse = true;
      loadExhibitor(parseInt(btn.dataset.id, 10));
    });
  });
}

function isDetailVisible() {
  return !$("detailSection").classList.contains("hidden");
}

function closeDetail() {
  $("detailSection").classList.add("hidden");
  currentExhibitorId = null;
  openedFromBrowse = false;
  if (pathExhibitorId() || qsId()) {
    history.replaceState({}, "", "/exhibitor");
  }
}

function handleBack() {
  if (isDetailVisible() && openedFromBrowse) {
    closeDetail();
    return;
  }
  if (typeof window.snecGoBackOrHome === "function") {
    window.snecGoBackOrHome();
  } else {
    location.href = "/";
  }
}

$("saveName").addEventListener("click", async () => {
  const display_name = $("displayName").value.trim() || "Anonymous";
  await api("/api/me", { method: "POST", body: JSON.stringify({ display_name }) });
  await refreshMe();
});

$("searchBtn").addEventListener("click", runSearch);
$("searchQ").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runSearch();
});

$("noteForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentExhibitorId) return;
  const note_detail = $("noteText").value.trim();
  if (!note_detail) return;
  await api(`/api/exhibitor/${currentExhibitorId}/notes`, {
    method: "POST",
    body: JSON.stringify({ note_detail }),
  });
  $("noteText").value = "";
  await loadExhibitor(currentExhibitorId);
});

$("imageForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!currentExhibitorId) return;
  const f = $("imageFile").files[0];
  if (!f) {
    alert("Choose an image first.");
    return;
  }
  const fd = new FormData();
  fd.append("file", f);
  fd.append("caption", $("imageCaption").value.trim());
  await api(`/api/exhibitor/${currentExhibitorId}/images`, { method: "POST", body: fd });
  $("imageFile").value = "";
  $("imageCaption").value = "";
  await loadExhibitor(currentExhibitorId);
});

$("backBtn")?.addEventListener("click", handleBack);

snecOnRegistered(async () => {
  try {
    await refreshMe();
    const id = initialExhibitorId();
    if (!Number.isNaN(id)) await loadExhibitor(id);
  } catch (err) {
    $("userMeta").textContent = `Error: ${err.message}`;
  }
});
