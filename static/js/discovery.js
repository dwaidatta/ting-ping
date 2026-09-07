/** Two independent modules on one page: sweep a subnet for live hosts, and
 *  probe one host's ports. Neither depends on the websocket — both are plain
 *  request/response scans the user triggers by hand. */
const discoveryUI = (() => {
  const COMMON_PORTS = "21,22,23,25,53,80,110,143,443,445,993,995,1723,3306,3389,5900,8080";

  const subnetForm = document.getElementById("discovery-form");
  const subnetInput = document.getElementById("d-subnet");
  const detectBtn = document.getElementById("btn-detect-subnet");
  const scanBtn = document.getElementById("btn-scan-network");
  const stopScanBtn = document.getElementById("btn-stop-scan");
  const discoveryProgress = document.getElementById("discovery-progress");
  const discoveryError = document.getElementById("discovery-error");
  const discoveryEmpty = document.getElementById("discovery-empty");
  const hostsSummary = document.getElementById("hosts-summary");
  const hostsGrid = document.getElementById("hosts-grid");

  const portForm = document.getElementById("portscan-form");
  const hostInput = document.getElementById("p-host");
  const portsInput = document.getElementById("p-ports");
  const presetSelect = document.getElementById("p-preset");
  const portScanBtn = document.getElementById("btn-scan-ports");
  const stopPortScanBtn = document.getElementById("btn-stop-portscan");
  const portscanProgress = document.getElementById("portscan-progress");
  const portscanError = document.getElementById("portscan-error");
  const portscanEmpty = document.getElementById("portscan-empty");
  const portsSummary = document.getElementById("ports-summary");
  const portsGrid = document.getElementById("ports-grid");

  // Each in-flight scan gets its own AbortController so its "stop" button
  // can cancel just that fetch — aborting closes the connection, which the
  // server's `finally` (see app/discovery.py) treats as a signal to cancel
  // whatever probes are still outstanding.
  let sweepController = null;
  let portScanController = null;

  function esc(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);
  }

  function setBusy(btn, progressEl, busy, label, stopBtn) {
    btn.disabled = busy;
    progressEl.hidden = !busy;
    if (busy) progressEl.innerHTML = `<span class="spinner"></span> ${label}`;
    if (stopBtn) stopBtn.hidden = !busy;
  }

  // ── network discovery ──────────────────────────────────────────────────

  async function detectSubnet() {
    detectBtn.disabled = true;
    try {
      const status = await api.getDeviceStatus();
      if (status.ipv4 && status.ipv4.cidr) {
        subnetInput.value = status.ipv4.cidr;
        discoveryError.hidden = true;
      } else {
        notify.toast("This machine has no active IPv4 subnet to read.", {
          title: "Could not detect subnet",
          tone: "warning",
        });
      }
    } catch (err) {
      notify.toast(err.message || "Could not read this machine's network status.", {
        title: "Detect failed",
      });
    } finally {
      detectBtn.disabled = false;
    }
  }

  function showDiscoveryError(message) {
    discoveryError.textContent = message;
    discoveryError.hidden = false;
  }

  function renderHosts(hosts) {
    const list = hosts || [];
    discoveryEmpty.hidden = list.length > 0;
    hostsGrid.hidden = list.length === 0;
    hostsSummary.hidden = list.length === 0;
    hostsSummary.textContent = `${list.length} host${list.length === 1 ? "" : "s"} answered`;

    hostsGrid.innerHTML = list
      .map(
        (h) => `
      <div class="host-card">
        <div class="host-card-head">
          <span class="status-dot up" title="Answered the sweep"><span class="dot-core"></span></span>
          <div class="host-ident">
            <div class="host-ip" title="Address">${esc(h.ip)}</div>
            <div class="host-hostname" title="Reverse-resolved hostname">${esc(h.hostname || "unresolved")}</div>
          </div>
          <button type="button" class="icon-btn btn-scan-this" data-ip="${esc(h.ip)}"
                  title="Send this address to the port scanner below">
            <i class="bi bi-hdd-network"></i>
          </button>
        </div>
        <div class="host-meta">
          ${h.mac ? `<span class="badge" title="MAC address">${esc(h.mac)}</span>` : "<span></span>"}
          <span class="latency-text" title="Round-trip time">${
            h.latency_ms != null ? `${Math.round(h.latency_ms)} ms` : "—"
          }</span>
        </div>
      </div>`
      )
      .join("");

    hostsGrid.querySelectorAll(".btn-scan-this").forEach((btn) => {
      btn.addEventListener("click", () => {
        hostInput.value = btn.dataset.ip;
        document.getElementById("portscan-panel").scrollIntoView({ behavior: "smooth", block: "start" });
        hostInput.focus();
      });
    });
  }

  async function runDiscovery(e) {
    e.preventDefault();
    discoveryError.hidden = true;

    const subnet = subnetInput.value.trim();
    if (!subnet) {
      showDiscoveryError("Enter an IPv4 subnet in CIDR form, e.g. 192.168.1.0/24.");
      return;
    }

    // Hosts render as each one answers rather than waiting for the full sweep;
    // the closing `done` event replaces this with the final sorted list (with
    // MAC addresses filled in, looked up once at the end).
    let hosts = [];
    renderHosts(hosts);

    const onEvent = (event) => {
      if (event.type === "host") {
        hosts = [...hosts, event.host];
        renderHosts(hosts);
      } else if (event.type === "done") {
        hosts = event.hosts;
        renderHosts(hosts);
      }
    };

    sweepController = new AbortController();
    setBusy(scanBtn, discoveryProgress, true, "sweeping subnet…", stopScanBtn);
    try {
      let force = false;
      while (true) {
        try {
          await api.streamDiscoverNetwork(subnet, onEvent, force, sweepController.signal);
          break;
        } catch (err) {
          if (err.name === "AbortError") {
            notify.toast("Sweep stopped — keeping the hosts found so far.", { tone: "warning", title: "Stopped" });
            break;
          }
          if (err.confirmRequired && (await notify.confirm({
            title: "large sweep",
            message: err.confirmMessage,
            confirmLabel: "scan anyway",
          }))) {
            force = true;
            continue;
          }
          if (!err.confirmRequired) showDiscoveryError(err.message || "The scan could not be completed.");
          break;
        }
      }
    } finally {
      setBusy(scanBtn, discoveryProgress, false, undefined, stopScanBtn);
      sweepController = null;
    }
  }

  // ── port scan ───────────────────────────────────────────────────────────

  function showPortscanError(message) {
    portscanError.textContent = message;
    portscanError.hidden = false;
  }

  // Closed/filtered ports aren't useful to a reader — only the ports that
  // actually answered are worth showing, and they render as soon as each one
  // is found rather than waiting for the whole scan to finish.
  function renderPorts(host, results) {
    const list = results || [];
    const open = list.filter((p) => p.state === "open");
    portscanEmpty.hidden = list.length > 0;
    portsGrid.hidden = list.length === 0;
    portsSummary.hidden = list.length === 0;
    portsSummary.textContent = `${esc(host)} · ${open.length} open / ${list.length} probed`;

    portsGrid.innerHTML = open
      .map(
        (p) => `
      <span class="port-chip open" title="${esc(p.service || "open")}">
        ${esc(p.port)}${p.service ? ` &middot; ${esc(p.service)}` : ""}
      </span>`
      )
      .join("");
  }

  presetSelect.addEventListener("change", () => {
    if (presetSelect.value === "common") portsInput.value = COMMON_PORTS;
    else if (presetSelect.value) portsInput.value = presetSelect.value;
    presetSelect.value = "";
  });

  async function runPortScan(e) {
    e.preventDefault();
    portscanError.hidden = true;

    const host = hostInput.value.trim();
    if (!host) {
      showPortscanError("Enter an IPv4 or IPv6 address to scan.");
      return;
    }
    const ports = portsInput.value.trim() || COMMON_PORTS;

    // Ports render as each one is probed rather than waiting for the whole
    // scan; the closing `done` event replaces this with the final list
    // sorted by port number.
    let results = [];
    renderPorts(host, results);

    const onEvent = (event) => {
      if (event.type === "port") {
        results = [...results, event.port];
        renderPorts(host, results);
      } else if (event.type === "done") {
        results = event.ports;
        renderPorts(host, results);
      }
    };

    portScanController = new AbortController();
    setBusy(portScanBtn, portscanProgress, true, "probing ports…", stopPortScanBtn);
    try {
      let force = false;
      while (true) {
        try {
          await api.streamScanPorts(host, ports, onEvent, force, portScanController.signal);
          break;
        } catch (err) {
          if (err.name === "AbortError") {
            notify.toast("Port scan stopped — keeping the ports found so far.", { tone: "warning", title: "Stopped" });
            break;
          }
          if (err.confirmRequired && (await notify.confirm({
            title: "large port scan",
            message: err.confirmMessage,
            confirmLabel: "scan anyway",
          }))) {
            force = true;
            continue;
          }
          if (!err.confirmRequired) showPortscanError(err.message || "The port scan could not be completed.");
          break;
        }
      }
    } finally {
      setBusy(portScanBtn, portscanProgress, false, undefined, stopPortScanBtn);
      portScanController = null;
    }
  }

  detectBtn.addEventListener("click", detectSubnet);
  subnetForm.addEventListener("submit", runDiscovery);
  portForm.addEventListener("submit", runPortScan);
  stopScanBtn.addEventListener("click", () => sweepController?.abort());
  stopPortScanBtn.addEventListener("click", () => portScanController?.abort());

  return {};
})();
