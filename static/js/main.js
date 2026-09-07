async function loadState() {
  const state = await api.getState();
  targetsUI.init(state.limits, state.status_codes);
  targetsUI.renderAll(state.targets);
}

/** Initial device snapshot: read for this client only, no broadcast. */
async function loadDeviceStatus() {
  devicePanel.showLoading();
  try {
    devicePanel.render(await api.getDeviceStatus());
  } catch (err) {
    devicePanel.showError(err.message);
  }
}

/** Manual refresh: re-reads and pushes the result to every connected client. */
async function refreshDeviceStatus() {
  devicePanel.showLoading();
  try {
    devicePanel.render(await api.refreshDeviceStatus());
  } catch (err) {
    devicePanel.showError(err.message);
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
    targetsUI.applyCheckResult(msg.target_id, msg.result, msg.uptime_ratio);
  });
  wsClient.onMessage("target_added", (msg) => targetsUI.upsertFromEvent(msg.target));
  wsClient.onMessage("target_updated", (msg) => targetsUI.upsertFromEvent(msg.target));
  wsClient.onMessage("target_removed", (msg) => targetsUI.removeCard(msg.target_id));
  wsClient.onMessage("targets_reordered", (msg) => targetsUI.applyOrder(msg.order));
  wsClient.onMessage("device_status", (msg) => devicePanel.render(msg.data));
  wsClient.onMessage("__reconnect__", () => loadState());
  wsClient.onStatus(setLinkStatus);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-refresh-device").addEventListener("click", refreshDeviceStatus);

  registerWsHandlers();
  wsClient.connect();

  // Both run unattended on page open; neither blocks the other.
  loadState().catch((err) => console.error("Failed to load initial state", err));
  loadDeviceStatus();
});
