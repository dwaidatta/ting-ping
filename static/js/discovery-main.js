function setLinkStatus(state) {
  const el = document.getElementById("link-status");
  const text = { online: "link up", offline: "link down", connecting: "connecting" }[state];
  el.className = `link-status ${state}`;
  el.querySelector(".link-text").textContent = text;
}

document.addEventListener("DOMContentLoaded", () => {
  wsClient.onStatus(setLinkStatus);
  wsClient.connect();
});
