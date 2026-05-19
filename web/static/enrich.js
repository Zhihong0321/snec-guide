(function () {
  const POLL_MS = 3000;

  function esc(s) {
    if (s == null || s === "") return "—";
    const d = document.createElement("div");
    d.textContent = String(s);
    return d.innerHTML;
  }

  function badge(text, kind) {
    return `<span class="enrich-badge enrich-badge--${kind}">${esc(text)}</span>`;
  }

  function renderStats(summary) {
    const el = document.getElementById("stats");
    if (!el || !summary) return;
    el.innerHTML = `
      <div class="enrich-stat"><span class="enrich-stat-n">${summary.pending}</span><span class="muted">Pending</span></div>
      <div class="enrich-stat enrich-stat--active"><span class="enrich-stat-n">${summary.in_progress}</span><span class="muted">In progress</span></div>
      <div class="enrich-stat enrich-stat--done"><span class="enrich-stat-n">${summary.done}</span><span class="muted">Done</span></div>
      <div class="enrich-stat"><span class="enrich-stat-n">${summary.total}</span><span class="muted">Total</span></div>
    `;
  }

  function renderWorkers(workers) {
    const el = document.getElementById("workers");
    if (!el) return;
    if (!workers || !workers.length) {
      el.innerHTML =
        '<p class="muted">No workers registered. Start <code>db_gemini_worker.py</code> or claim from Cursor.</p>';
      return;
    }
    el.innerHTML = workers
      .map((w) => {
        const stale = w.stale ? badge("stale?", "warn") : "";
        const statusKind = w.status === "working" ? "active" : "idle";
        const ex = w.exhibitor;
        const exLine = ex
          ? `<p class="enrich-worker-ex"><a href="/exhibitor/${ex.id}">#${ex.id} ${esc(ex.company_name_cn)}</a> <span class="muted">${esc(ex.booth_display || ex.hall || "")}</span></p>`
          : '<p class="muted small">Idle — waiting for next claim</p>';
        return `
          <article class="enrich-worker-card ${w.status === "working" ? "is-working" : ""}">
            <div class="enrich-worker-head">
              <strong>${esc(w.agent_id)}</strong>
              ${badge(w.worker_label || w.worker_type, "type")}
              ${badge(w.status, statusKind)}
              ${stale}
            </div>
            ${exLine}
            <p class="muted small">PID ${esc(w.pid)} · ${esc(w.hostname)} · seen ${esc(w.last_seen_at)}</p>
          </article>
        `;
      })
      .join("");
  }

  function renderLocked(rows) {
    const el = document.getElementById("locked");
    if (!el) return;
    if (!rows || !rows.length) {
      el.innerHTML = '<p class="muted">No exhibitors locked right now.</p>';
      return;
    }
    el.innerHTML = `
      <table class="enrich-table">
        <thead><tr><th>Agent</th><th>Engine</th><th>Exhibitor</th><th>Updated</th></tr></thead>
        <tbody>
          ${rows
            .map(
              (r) => `
            <tr>
              <td><code>${esc(r.enrichment_status)}</code></td>
              <td>${badge(r.worker_label || "—", "type")}</td>
              <td><a href="/exhibitor/${r.id}">#${r.id} ${esc(r.company_name_cn)}</a></td>
              <td class="muted small">${esc(r.updated_at)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  function renderRecent(rows) {
    const el = document.getElementById("recent");
    if (!el) return;
    if (!rows || !rows.length) {
      el.innerHTML = '<p class="muted">No completed rows yet.</p>';
      return;
    }
    el.innerHTML = `
      <table class="enrich-table">
        <thead><tr><th>ID</th><th>Company</th><th>Engine</th><th>Done at</th></tr></thead>
        <tbody>
          ${rows
            .map(
              (r) => `
            <tr>
              <td><a href="/exhibitor/${r.id}">${r.id}</a></td>
              <td>${esc(r.company_name_cn)}</td>
              <td>${badge(r.worker_label || "—", "type")}</td>
              <td class="muted small">${esc(r.enriched_at)}</td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  async function refresh() {
    const lr = document.getElementById("lastRefresh");
    try {
      const res = await fetch("/api/enrichment/dashboard");
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      renderStats(data.summary);
      renderWorkers(data.workers);
      renderLocked(data.locked_exhibitors);
      renderRecent(data.recent_done);
      if (lr) lr.textContent = `Updated ${new Date().toLocaleTimeString()}`;
    } catch (e) {
      if (lr) lr.textContent = `Error: ${e.message}`;
    }
  }

  let timer = null;
  function schedule() {
    if (timer) clearInterval(timer);
    const on = document.getElementById("autoRefresh")?.checked;
    if (on) timer = setInterval(refresh, POLL_MS);
  }

  document.getElementById("autoRefresh")?.addEventListener("change", schedule);
  refresh();
  schedule();
})();
