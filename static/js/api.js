const api = (() => {
  async function request(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      throw await toApiError(res);
    }
    if (res.status === 204) return null;
    return res.json();
  }

  /** A 409 with `{confirm_required: true, message}` means the request is
   *  valid but large enough to be worth a second thought — the caller can
   *  inspect `err.confirmRequired`/`err.confirmMessage` and re-send with
   *  `force: true` once the user says to go ahead anyway. Any other shape
   *  is treated as a plain, non-confirmable error. */
  async function toApiError(res) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (data.detail && typeof data.detail === "object" && data.detail.confirm_required) {
        const err = new Error(data.detail.message || detail);
        err.confirmRequired = true;
        err.confirmMessage = data.detail.message;
        return err;
      }
      detail = data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : detail;
    } catch (_) {}
    return new Error(detail || `Request failed: ${res.status}`);
  }

  /** POSTs `body`, then reads the response as newline-delimited JSON, calling
   *  `onEvent` with each parsed line as it arrives instead of waiting for the
   *  whole body. Passing `signal` (an AbortController's) lets the caller stop
   *  the scan early — the fetch rejects with a DOMException named
   *  "AbortError", which the caller can check for instead of treating it as
   *  a real failure. */
  async function requestStream(method, path, body, onEvent, signal) {
    const res = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok) {
      throw await toApiError(res);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (line) onEvent(JSON.parse(line));
      }
    }
    const rest = buffer.trim();
    if (rest) onEvent(JSON.parse(rest));
  }

  return {
    getState: () => request("GET", "/api/state"),
    getTargets: () => request("GET", "/api/targets"),
    createTarget: (payload) => request("POST", "/api/targets", payload),
    updateTarget: (id, payload) => request("PUT", `/api/targets/${id}`, payload),
    deleteTarget: (id) => request("DELETE", `/api/targets/${id}`),
    // Full list of target ids in their new grid order; persisted to targets.json.
    reorderTargets: (order) => request("PUT", "/api/targets/order", { order }),
    // GET reads a snapshot for this client only; POST re-reads and broadcasts to every client.
    getDeviceStatus: () => request("GET", "/api/device-status"),
    refreshDeviceStatus: () => request("POST", "/api/device-status"),
    // Network discovery: sweep a subnet or probe one host's ports, each
    // streamed as NDJSON — one event per host/port as it's discovered, plus a
    // final `done` event.
    streamDiscoverNetwork: (subnet, onEvent, force = false, signal) =>
      requestStream("POST", "/api/discovery/scan", { subnet, force }, onEvent, signal),
    streamScanPorts: (host, ports, onEvent, force = false, signal) =>
      requestStream("POST", "/api/discovery/port-scan", { host, ports, force }, onEvent, signal),
  };
})();
