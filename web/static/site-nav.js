/** Shared site navigation — mobile bottom tab bar + header register CTA.
 *  Each page sets body[data-nav-active] to highlight the current tab. */
(function () {
  // Inline icon set (stroke = currentColor)
  const ICON = {
    home: '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/><path d="M9.5 21v-6h5v6"/>',
    chat: '<path d="M21 11.5a8 8 0 0 1-11.6 7.1L4 20l1.4-4.4A8 8 0 1 1 21 11.5Z"/>',
    guides: '<path d="m9 4-6 2.5v14L9 18l6 3 6-2.5v-14L15 7"/><path d="M9 4v14"/><path d="M15 7v14"/>',
    visit: '<path d="M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
    register: '<path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><path d="m10 17 5-5-5-5"/><path d="M15 12H3"/>',
  };

  const TABS = [
    { id: "home", href: "/", label: "Home", icon: "home" },
    { id: "chat", href: "/chat", label: "AI Chat", icon: "chat" },
    { id: "guides", href: "/maps", label: "Guides", icon: "guides" },
    { id: "visit", href: "/exhibitor", label: "Visit Log", icon: "visit" },
  ];

  const REGISTER_URL = "https://pv.snec.org.cn/proRegister?locale=en-US";

  function svg(name) {
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name]}</svg>`;
  }

  function renderHeaderCta() {
    const nav = document.getElementById("siteNav");
    if (!nav) return;
    nav.innerHTML =
      `<a class="nav-cta" href="${REGISTER_URL}" target="_blank" rel="noopener noreferrer">` +
      `${svg("register")}<span>Register</span></a>`;
  }

  function renderTabBar() {
    if (document.querySelector(".tabbar")) return;
    const active = document.body.dataset.navActive || "";
    const bar = document.createElement("nav");
    bar.className = "tabbar";
    bar.setAttribute("aria-label", "Primary");
    bar.innerHTML =
      '<div class="tabbar-inner">' +
      TABS.map((t) => {
        const cls = t.id === active ? "tab active" : "tab";
        const cur = t.id === active ? ' aria-current="page"' : "";
        return (
          `<a class="${cls}" href="${t.href}"${cur}>` +
          `<span class="tab-ico">${svg(t.icon)}</span>` +
          `<span>${t.label}</span></a>`
        );
      }).join("") +
      "</div>";
    document.body.appendChild(bar);
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

  function init() {
    renderHeaderCta();
    renderTabBar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
