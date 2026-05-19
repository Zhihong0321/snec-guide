const $ = (id) => document.getElementById(id);

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s == null ? "" : String(s);
  return d.innerHTML;
}

function formatWhen(iso) {
  if (!iso) return "";
  const s = String(iso).replace("T", " ").slice(0, 19);
  return s;
}

function boothLabel(ex) {
  return ex.booth_display || [ex.hall, ex.booth].filter(Boolean).join(" ") || "";
}

function renderExhibitorLink(ex) {
  const name = esc(ex.company_name_cn || ex.company_name_en || "Exhibitor");
  const booth = boothLabel(ex);
  const meta = booth ? ` · ${esc(booth)}` : "";
  return `<a class="feed-exhibitor" href="/exhibitor/${ex.id}">${name}${meta}</a>`;
}

function renderNote(item) {
  return `
    <article class="feed-card feed-card-note">
      <div class="feed-card-head">
        <span class="feed-badge">Note</span>
        <span class="feed-meta">${esc(item.author)} · ${esc(formatWhen(item.created_at))}</span>
      </div>
      ${renderExhibitorLink(item.exhibitor)}
      <p class="feed-body">${esc(item.body)}</p>
    </article>
  `;
}

function renderImage(item) {
  const url = esc(item.image_url || item.image_path || "");
  const cap = item.caption ? `<p class="feed-caption">${esc(item.caption)}</p>` : "";
  return `
    <article class="feed-card feed-card-image">
      <div class="feed-card-head">
        <span class="feed-badge feed-badge-image">Photo</span>
        <span class="feed-meta">${esc(item.author)} · ${esc(formatWhen(item.created_at))}</span>
      </div>
      ${renderExhibitorLink(item.exhibitor)}
      <a class="feed-image-link" href="${url}" target="_blank" rel="noopener">
        <img src="${url}" alt="" loading="lazy" />
      </a>
      ${cap}
    </article>
  `;
}

function renderFeed(items) {
  const el = $("feed");
  if (!items.length) {
    el.innerHTML = `
      <section class="panel feed-empty">
        <p>No updates yet.</p>
        <p class="muted small">Add notes or photos on the <a href="/exhibitor">visit log</a> — they will show up here for everyone.</p>
      </section>
    `;
    return;
  }
  el.innerHTML = items
    .map((item) => (item.type === "image" ? renderImage(item) : renderNote(item)))
    .join("");
}

async function loadFeed() {
  const status = $("feedStatus");
  const btn = $("refreshFeed");
  status.textContent = "Loading…";
  if (btn) btn.disabled = true;
  try {
    const data = await fetch("/api/feed?limit=40").then((r) => {
      if (!r.ok) throw new Error(r.statusText);
      return r.json();
    });
    renderFeed(data.items || []);
    status.textContent = data.items?.length
      ? `${data.items.length} recent update${data.items.length === 1 ? "" : "s"}`
      : "";
  } catch (e) {
    $("feed").innerHTML = `<section class="panel feed-empty"><p class="warn">Could not load feed: ${esc(e.message)}</p></section>`;
    status.textContent = "";
  } finally {
    if (btn) btn.disabled = false;
  }
}

$("refreshFeed")?.addEventListener("click", loadFeed);
loadFeed();
