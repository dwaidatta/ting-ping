const wsClient = (() => {
  const handlers = new Map();
  let socket = null;
  let backoff = 1000;
  const maxBackoff = 10000;
  let hasConnectedBefore = false;
  let statusHandler = null;

  function onMessage(type, handler) {
    handlers.set(type, handler);
  }

  /** Reports "connecting" | "online" | "offline" so the header can show the feed state. */
  function onStatus(handler) {
    statusHandler = handler;
  }

  function setStatus(state) {
    if (statusHandler) statusHandler(state);
  }

  function connect() {
    setStatus("connecting");
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${protocol}//${location.host}/ws`);

    socket.addEventListener("open", () => {
      backoff = 1000;
      setStatus("online");
      if (hasConnectedBefore) {
        const onReconnect = handlers.get("__reconnect__");
        if (onReconnect) onReconnect();
      }
      hasConnectedBefore = true;
    });

    socket.addEventListener("message", (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (_) {
        return;
      }
      const handler = handlers.get(msg.type);
      if (handler) handler(msg);
    });

    socket.addEventListener("close", () => {
      setStatus("offline");
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, maxBackoff);
    });

    socket.addEventListener("error", () => {
      socket.close();
    });
  }

  return { onMessage, onStatus, connect };
})();
