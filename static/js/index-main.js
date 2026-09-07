const dashStats = (() => {
  // id -> { enabled, success (null = no result yet), uptimeRatio }
  const targets = new Map();

  function statusOf(entry) {
    if (!entry.enabled) return "unknown";
    if (entry.success === null) return "unknown";
    return entry.success ? "up" : "down";
  }

  function render() {
    let up = 0, down = 0, unknown = 0;
    let uptimeSum = 0, uptimeCount = 0;

    for (const entry of targets.values()) {
      const status = statusOf(entry);
      if (status === "up") up++;
      else if (status === "down") down++;
      else unknown++;
      if (entry.uptimeRatio !== null && entry.uptimeRatio !== undefined) {
        uptimeSum += entry.uptimeRatio;
        uptimeCount++;
      }
    }

    const total = targets.size;
    document.getElementById("stat-total").textContent = total;
    document.getElementById("stat-up").textContent = up;
    document.getElementById("stat-down").textContent = down;
    document.getElementById("stat-unknown").textContent = unknown;
    document.getElementById("stat-uptime").textContent =
      uptimeCount ? `${Math.round((uptimeSum / uptimeCount) * 100)}%` : "n/a";

    const meta = document.getElementById("dash-monitors-meta");
    if (total === 0) {
      meta.innerHTML = "no monitors defined yet";
    } else {
      meta.innerHTML =
        `<span class="${up ? "ok" : ""}">${up} up</span> &middot; ` +
        `<span class="${down ? "bad" : ""}">${down} down</span> &middot; ` +
        `${unknown} idle`;
    }
  }

  function loadFromState(state) {
    targets.clear();
    for (const [id, entry] of Object.entries(state.targets)) {
      const last = entry.buffer.length ? entry.buffer[entry.buffer.length - 1] : null;
      targets.set(id, {
        enabled: entry.target.enabled,
        success: last ? last.success : null,
        uptimeRatio: entry.uptime_ratio,
      });
    }
    render();
  }

  function applyCheckResult(id, result, uptimeRatio) {
    const entry = targets.get(id);
    if (!entry) return;
    entry.success = result.success;
    entry.uptimeRatio = uptimeRatio;
    render();
  }

  function upsertFromEvent(target) {
    const existing = targets.get(target.id);
    targets.set(target.id, {
      enabled: target.enabled,
      success: existing ? existing.success : null,
      uptimeRatio: existing ? existing.uptimeRatio : null,
    });
    render();
  }

  function removeTarget(id) {
    targets.delete(id);
    render();
  }

  return { loadFromState, applyCheckResult, upsertFromEvent, removeTarget };
})();

function renderDeviceMeta(data) {
  const meta = document.getElementById("dash-device-meta");
  const net = data.connectivity?.internet || {};
  const iface = data.interface || {};
  const netTone = net.reachable === true ? "ok" : net.reachable === false ? "bad" : "";
  const ifaceTone = iface.isup === true ? "ok" : iface.isup === false ? "bad" : "";
  const netText = net.reachable === true ? "online" : net.reachable === false ? "offline" : "unknown";
  const ifaceText = iface.isup === true ? "up" : iface.isup === false ? "down" : "unknown";
  meta.innerHTML =
    `internet <span class="${netTone}">${netText}</span> &middot; ` +
    `adapter <span class="${ifaceTone}">${ifaceText}</span>`;
}

async function loadDashboard() {
  const state = await api.getState();
  dashStats.loadFromState(state);
}

async function loadDeviceMeta() {
  try {
    const data = await api.getDeviceStatus();
    renderDeviceMeta(data);
  } catch (err) {
    document.getElementById("dash-device-meta").textContent = "could not read device status";
  }
}

function setLinkStatus(state) {
  const el = document.getElementById("link-status");
  const text = { online: "link up", offline: "link down", connecting: "connecting" }[state];
  el.className = `link-status ${state}`;
  el.querySelector(".link-text").textContent = text;
}

function registerWsHandlers() {
  wsClient.onMessage("check_result", (msg) => {
    dashStats.applyCheckResult(msg.target_id, msg.result, msg.uptime_ratio);
  });
  wsClient.onMessage("target_added", (msg) => dashStats.upsertFromEvent(msg.target));
  wsClient.onMessage("target_updated", (msg) => dashStats.upsertFromEvent(msg.target));
  wsClient.onMessage("target_removed", (msg) => dashStats.removeTarget(msg.target_id));
  wsClient.onMessage("device_status", (msg) => renderDeviceMeta(msg.data));
  wsClient.onMessage("__reconnect__", () => loadDashboard());
  wsClient.onStatus(setLinkStatus);
}

document.addEventListener("DOMContentLoaded", () => {
  registerWsHandlers();
  wsClient.connect();

  loadDashboard().catch((err) =>
    notify.toast(err.message || "Could not load monitors from the server.", { title: "Failed to load state" })
  );
  loadDeviceMeta();
});
