/** Block app until visitor sets a display name (cookie + DB). */
(function () {
  const OVERLAY_ID = "regGate";
  const readyCallbacks = [];
  let readyFired = false;

  function isRegistered(me) {
    if (me && me.registered === true) return true;
    return Boolean(((me && me.display_name) || "").trim());
  }

  async function fetchMe() {
    const res = await fetch("/api/me", { credentials: "include" });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t || res.statusText);
    }
    return res.json();
  }

  async function saveName(displayName) {
    const res = await fetch("/api/me", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: displayName }),
    });
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t || res.statusText);
    }
    return res.json();
  }

  function fireReady(me) {
    if (readyFired) return;
    readyFired = true;
    window.__snecMe = me;
    document.body.classList.remove("reg-locked");
    const overlay = document.getElementById(OVERLAY_ID);
    if (overlay) overlay.remove();
    for (const fn of readyCallbacks) {
      try {
        fn(me);
      } catch (err) {
        console.error(err);
      }
    }
    document.dispatchEvent(new CustomEvent("snec:registered", { detail: me }));
  }

  window.snecOnRegistered = function (fn) {
    if (readyFired) fn(window.__snecMe);
    else readyCallbacks.push(fn);
  };

  function buildOverlay() {
    const el = document.createElement("div");
    el.id = OVERLAY_ID;
    el.className = "reg-gate";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-labelledby", "regGateTitle");
    el.innerHTML = `
      <div class="reg-gate-card">
        <div class="logo reg-gate-logo" aria-hidden="true">☀</div>
        <h2 id="regGateTitle" class="reg-gate-title">Welcome to SNEC 2026</h2>
        <p class="reg-gate-lead">Enter your name to continue. We will save it in a <strong>browser cookie</strong> on this device so notes and visits stay tied to you — no password or account signup.</p>
        <form id="regGateForm" class="reg-gate-form">
          <label class="sr-only" for="regGateName">Your name</label>
          <input
            type="text"
            id="regGateName"
            class="input"
            placeholder="Your name"
            maxlength="100"
            required
            autocomplete="name"
          />
          <p id="regGateError" class="reg-gate-error hidden" role="alert"></p>
          <button type="submit" class="btn-primary reg-gate-submit">Continue</button>
        </form>
        <p class="muted small reg-gate-foot">Cookie name: <code>snec_uid</code> · HttpOnly · 1 year</p>
      </div>
    `;
    return el;
  }

  function showError(overlay, message) {
    const err = overlay.querySelector("#regGateError");
    err.textContent = message;
    err.classList.remove("hidden");
  }

  async function runGate() {
    let me;
    try {
      me = await fetchMe();
    } catch (err) {
      me = { registered: false, display_name: "" };
    }

    if (isRegistered(me)) {
      fireReady(me);
      return;
    }

    document.body.classList.add("reg-locked");
    const overlay = buildOverlay();
    document.body.appendChild(overlay);

    const form = overlay.querySelector("#regGateForm");
    const input = overlay.querySelector("#regGateName");
    const submitBtn = overlay.querySelector(".reg-gate-submit");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = input.value.trim();
      if (!name) {
        showError(overlay, "Please enter your name.");
        input.focus();
        return;
      }
      submitBtn.disabled = true;
      overlay.querySelector("#regGateError").classList.add("hidden");
      try {
        me = await saveName(name);
        fireReady(me);
      } catch (err) {
        showError(overlay, err.message || "Could not save your name.");
        submitBtn.disabled = false;
      }
    });

    input.focus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runGate);
  } else {
    runGate();
  }
})();
