const $ = (id) => document.getElementById(id);

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function formatSize(bytes) {
  if (!bytes) return "";
  if (bytes >= 1_000_000) return `${(bytes / 1_000_000).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

function renderPdfs(pdfs) {
  const el = $("pdfList");
  if (!pdfs.length) {
    el.innerHTML = `<li class="pdf-item muted">PDF files not found on the server.</li>`;
    return;
  }
  el.innerHTML = pdfs
    .map(
      (p) => `
    <li class="pdf-item">
      <div class="pdf-item-text">
        <strong>${esc(p.title)}</strong>
        <span class="muted small">${esc(p.description)} · ${esc(p.size_label || formatSize(p.size_bytes))}</span>
      </div>
      <a class="btn-primary pdf-download" href="${esc(p.url)}" download="${esc(p.filename)}">Download</a>
    </li>
  `
    )
    .join("");
}

let allMaps = [];

function renderMaps(items) {
  const grid = $("mapGrid");
  if (!items.length) {
    grid.innerHTML = `<p class="muted">No floor plan images in <code>floor_plans/</code>.</p>`;
    return;
  }
  grid.innerHTML = items
    .map(
      (m) => `
    <button type="button" class="map-card" data-url="${esc(m.url)}" data-label="${esc(m.label)}">
      <img src="${esc(m.url)}" alt="${esc(m.label)}" loading="lazy" />
      <span class="map-card-label">${esc(m.hall)}</span>
      <span class="map-card-sub">${esc(m.label)}</span>
    </button>
  `
    )
    .join("");

  grid.querySelectorAll(".map-card").forEach((btn) => {
    btn.addEventListener("click", () => openLightbox(btn.dataset.url, btn.dataset.label));
  });
}

function openLightbox(url, label) {
  const dlg = $("mapLightbox");
  $("mapLightboxImg").src = url;
  $("mapLightboxImg").alt = label;
  $("mapLightboxTitle").textContent = label;
  $("mapLightboxOpen").href = url;
  if (typeof dlg.showModal === "function") dlg.showModal();
  else window.open(url, "_blank", "noopener");
}

function closeLightbox() {
  const dlg = $("mapLightbox");
  if (dlg.open) dlg.close();
  $("mapLightboxImg").src = "";
}

$("mapLightboxClose")?.addEventListener("click", closeLightbox);
$("mapLightbox")?.addEventListener("click", (e) => {
  if (e.target === $("mapLightbox")) closeLightbox();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeLightbox();
});

$("mapFilter")?.addEventListener("input", (e) => {
  const q = e.target.value.trim().toLowerCase();
  if (!q) {
    renderMaps(allMaps);
    return;
  }
  renderMaps(
    allMaps.filter(
      (m) =>
        m.hall.toLowerCase().includes(q) ||
        m.label.toLowerCase().includes(q) ||
        m.filename.toLowerCase().includes(q)
    )
  );
});

async function loadMaps() {
  try {
    const data = await fetch("/api/maps").then((r) => {
      if (!r.ok) throw new Error(r.statusText);
      return r.json();
    });
    renderPdfs(data.pdfs || []);
    allMaps = data.floor_plans || [];
    renderMaps(allMaps);
  } catch (e) {
    $("pdfList").innerHTML = `<li class="pdf-item warn">Could not load: ${esc(e.message)}</li>`;
    $("mapGrid").innerHTML = "";
  }
}

loadMaps();
