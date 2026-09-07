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

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btn-refresh-device").addEventListener("click", refreshDeviceStatus);

  wsClient.onMessage("device_status", (msg) => devicePanel.render(msg.data));
  wsClient.onMessage("__reconnect__", () => loadDeviceStatus());
  wsClient.onStatus(setLinkStatus);
  wsClient.connect();

  loadDeviceStatus();
});
