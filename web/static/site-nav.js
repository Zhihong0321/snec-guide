/** Shared site navigation — set body[data-nav-active] on each page. */
(function () {
  const ITEMS = [
    { id: "home", href: "/", label: "Home" },
    { id: "enrich", href: "/enrich", label: "Enrichment" },
    { id: "chat", href: "/chat", label: "AI chat" },
    { id: "guides", href: "/maps", label: "Guides" },
    { id: "visit", href: "/exhibitor", label: "Visit log" },
  ];

  function renderNav() {
    const nav = document.getElementById("siteNav");
    if (!nav) return;
    const active = document.body.dataset.navActive || "";
    nav.innerHTML = ITEMS.map((item) => {
      const cls = item.id === active ? ' class="active"' : "";
      return `<a href="${item.href}"${cls}>${item.label}</a>`;
    }).join("");
  }

  /** Same-origin history step, else home. */
  function goBackOrHome() {
    try {
      const ref = document.referrer;
      if (ref && new URL(ref).origin === location.origin && window.history.length > 1) {
        history.back();
        return;
      }
    } catch (_) {
      /* ignore bad referrer */
    }
    location.href = "/";
  }

  window.snecGoBackOrHome = goBackOrHome;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderNav);
  } else {
    renderNav();
  }
})();
