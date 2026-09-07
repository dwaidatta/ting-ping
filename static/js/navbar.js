/** Shared topbar/sidebar, injected into <header id="app-header"></header> and
 *  <aside id="app-sidebar"></aside> on every page. One copy of the markup
 *  means the tabs can't drift out of sync between pages the way four
 *  hand-copied navs eventually would. */
(function () {
  const tabs = [
    { href: "/", icon: "bi-house", label: "home" },
    { href: "/monitor", icon: "bi-activity", label: "monitors" },
    { href: "/device", icon: "bi-hdd-network", label: "device status" },
    { href: "/discovery", icon: "bi-search", label: "discovery" },
    { href: "/traceroute", icon: "bi-signpost-split", label: "traceroute" },
    { href: "/resolver", icon: "bi-globe2", label: "resolver" },
  ];

  const path = location.pathname;
  const navHtml = tabs
    .map((t) => {
      const active = t.href === path ? " active" : "";
      return `<a href="${t.href}" class="nav-tab${active}" title="${t.label}">
        <i class="bi ${t.icon}"></i><span class="nav-label">${t.label}</span>
      </a>`;
    })
    .join("\n      ");

  const sidebar = document.getElementById("app-sidebar");
  const header = document.getElementById("app-header");
  if (!sidebar || !header) return;

  header.innerHTML = `
    <div class="header-left">
      <button id="sidebar-mobile-toggle" class="icon-btn sidebar-mobile-btn" aria-label="Open menu" title="Open menu">
        <i class="bi bi-list"></i>
      </button>
      <div class="brand">
        <span class="brand-prompt">root@tingping</span><span class="brand-sep">:</span><span class="brand-path">~</span><span class="brand-caret">#</span>
        <span class="brand-name">ting-ping</span>
        <span class="brand-tag">network reachability monitor</span>
      </div>
    </div>

    <div class="header-actions">
      <div id="link-status" class="link-status" title="Live websocket feed shared across pages, pushing check and device-status updates. If it drops, the page reconnects on its own.">
        <span class="link-dot"></span><span class="link-text">connecting</span>
      </div>
    </div>`;

  sidebar.innerHTML = `
    <nav class="sidebar-nav">
      ${navHtml}
    </nav>

    <div class="sidebar-footer">
      <button id="sidebar-collapse-toggle" class="icon-btn sidebar-collapse-btn"
              aria-label="Collapse sidebar" title="Collapse sidebar">
        <i class="bi bi-chevron-double-left"></i>
      </button>
    </div>`;

  // The sidebar sits below the topbar and is pinned to its own bottom edge
  // (position: sticky/fixed with `top: var(--header-h)`), so it needs the
  // topbar's real rendered height, not the CSS fallback.
  function syncHeaderHeight() {
    document.documentElement.style.setProperty("--header-h", `${header.offsetHeight}px`);
  }
  syncHeaderHeight();
  window.addEventListener("resize", syncHeaderHeight);

  // ── desktop collapse/expand, persisted across pages ──────────────────
  const STORAGE_KEY = "tp-sidebar-collapsed";
  const collapseBtn = document.getElementById("sidebar-collapse-toggle");

  function setCollapsed(collapsed) {
    sidebar.classList.toggle("collapsed", collapsed);
    try {
      localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
    } catch (e) {
      /* localStorage unavailable (private mode, etc.) — collapsed state just won't persist */
    }
    collapseBtn.querySelector("i").className = collapsed
      ? "bi bi-chevron-double-right"
      : "bi bi-chevron-double-left";
    const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
    collapseBtn.title = label;
    collapseBtn.setAttribute("aria-label", label);
  }

  let storedCollapsed = false;
  try {
    storedCollapsed = localStorage.getItem(STORAGE_KEY) === "1";
  } catch (e) {
    /* localStorage unavailable (private mode, etc.) — default to expanded */
  }
  // Restoring the persisted state on a fresh page load is not a user
  // action — suppress the width transition so it doesn't visibly
  // collapse/expand on every navigation, then re-enable it for later clicks.
  sidebar.classList.add("no-transition");
  setCollapsed(storedCollapsed);
  void sidebar.offsetWidth;
  sidebar.classList.remove("no-transition");

  collapseBtn.addEventListener("click", () => {
    setCollapsed(!sidebar.classList.contains("collapsed"));
  });

  // ── mobile off-canvas drawer ──────────────────────────────────────────
  let backdrop = document.getElementById("sidebar-backdrop");
  if (!backdrop) {
    backdrop = document.createElement("div");
    backdrop.id = "sidebar-backdrop";
    backdrop.className = "sidebar-backdrop";
    document.body.appendChild(backdrop);
  }

  function openMobile() {
    sidebar.classList.add("mobile-open");
    backdrop.classList.add("visible");
  }
  function closeMobile() {
    sidebar.classList.remove("mobile-open");
    backdrop.classList.remove("visible");
  }

  document.getElementById("sidebar-mobile-toggle").addEventListener("click", openMobile);
  backdrop.addEventListener("click", closeMobile);
})();
