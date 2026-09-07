async function loadState() {
  const state = await api.getState();
  targetsUI.init(state.limits, state.status_codes);
  targetsUI.renderAll(state.targets);
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
  wsClient.onMessage("__reconnect__", () => loadState());
  wsClient.onStatus(setLinkStatus);
}

document.addEventListener("DOMContentLoaded", () => {
  registerWsHandlers();
  wsClient.connect();

  loadState().catch((err) =>
    notify.toast(err.message || "Could not load monitors from the server.", { title: "Failed to load state" })
  );
});
