/** Shared header/nav, injected into <header id="app-header"></header> on
 *  every page. One copy of the markup means the tabs can't drift out of
 *  sync between pages the way four hand-copied headers eventually would. */
(function () {
  const tabs = [
    { href: "/", icon: "bi-house", label: "home" },
    { href: "/monitor", icon: "bi-activity", label: "monitors" },
    { href: "/device", icon: "bi-hdd-network", label: "device status" },
    { href: "/discovery", icon: "bi-search", label: "discovery" },
  ];

  const path = location.pathname;
  const navHtml = tabs
    .map((t) => {
      const active = t.href === path ? " active" : "";
      return `<a href="${t.href}" class="nav-tab${active}"><i class="bi ${t.icon}"></i> ${t.label}</a>`;
    })
    .join("\n      ");

  const header = document.getElementById("app-header");
  if (!header) return;

  header.innerHTML = `
    <div class="brand">
      <span class="brand-prompt">root@tingping</span><span class="brand-sep">:</span><span class="brand-path">~</span><span class="brand-caret">#</span>
      <span class="brand-name">ting-ping</span>
      <span class="brand-tag">network reachability monitor</span>
    </div>

    <nav class="page-nav">
      ${navHtml}
    </nav>

    <div class="header-actions">
      <div id="link-status" class="link-status" title="Live websocket feed shared across pages, pushing check and device-status updates. If it drops, the page reconnects on its own.">
        <span class="link-dot"></span><span class="link-text">connecting</span>
      </div>
    </div>`;
})();
