const api = (() => {
  async function request(method, path, body) {
    const res = await fetch(path, {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const data = await res.json();
        detail = data.detail ? JSON.stringify(data.detail) : detail;
      } catch (_) {}
      throw new Error(detail || `Request failed: ${res.status}`);
    }
    if (res.status === 204) return null;
    return res.json();
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
  };
})();
