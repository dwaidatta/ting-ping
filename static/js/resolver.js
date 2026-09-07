/** One lookup at a time, a plain request/response (no streaming — both the
 *  forward and reverse paths are single fast calls), mirroring the busy-state
 *  pattern discovery.js uses for its scans. */
const resolverUI = (() => {
  const form = document.getElementById("resolver-form");
  const queryInput = document.getElementById("r-query");
  const resolveBtn = document.getElementById("btn-resolve");
  const progress = document.getElementById("resolver-progress");
  const errorEl = document.getElementById("resolver-error");
  const emptyEl = document.getElementById("resolver-empty");
  const output = document.getElementById("resolver-output");

  function esc(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);
  }

  function setBusy(busy) {
    resolveBtn.disabled = busy;
    progress.hidden = !busy;
    if (busy) progress.innerHTML = `<span class="spinner"></span> resolving…`;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function addressGroup(label, addresses) {
    if (!addresses.length) return "";
    const chips = addresses
      .map(
        (a) => `
      <span class="port-chip open resolve-chip" data-addr="${esc(a)}" title="Resolve this address">
        ${esc(a)}
      </span>`
      )
      .join("");
    return `
      <div class="resolve-group">
        <div class="resolve-group-title">${label}</div>
        <div class="ports-grid">${chips}</div>
      </div>`;
  }

  function renderHostname(result) {
    const canonical = result.canonical_name
      ? `<div class="scan-summary muted">canonical name: ${esc(result.canonical_name)}</div>`
      : "";
    const latency = `<div class="scan-summary muted">resolved in ${Math.round(result.latency_ms)} ms</div>`;
    const groups = addressGroup("IPv4", result.addresses.ipv4) + addressGroup("IPv6", result.addresses.ipv6);
    const none = !result.addresses.ipv4.length && !result.addresses.ipv6.length
      ? `<p class="muted">No addresses returned.</p>`
      : "";
    output.innerHTML = canonical + latency + groups + none;
  }

  function renderIp(result) {
    const label = result.version === 6 ? "IPv6" : "IPv4";
    const body = result.hostname
      ? `<div class="resolve-group">
          <div class="resolve-group-title">${label} &middot; PTR record</div>
          <div class="ports-grid">
            <span class="port-chip open resolve-chip" data-addr="${esc(result.hostname)}" title="Resolve this hostname">
              ${esc(result.hostname)}
            </span>
          </div>
        </div>`
      : `<p class="muted">No PTR record for ${esc(result.query)}.</p>`;
    output.innerHTML = body;
  }

  function bindChips() {
    output.querySelectorAll(".resolve-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        queryInput.value = chip.dataset.addr;
        form.requestSubmit();
      });
    });
  }

  async function runResolve(e) {
    e.preventDefault();
    errorEl.hidden = true;

    const query = queryInput.value.trim();
    if (!query) {
      showError("Enter a hostname or IP address to resolve.");
      return;
    }

    setBusy(true);
    try {
      const result = await api.resolveQuery(query);
      emptyEl.hidden = true;
      output.hidden = false;
      if (result.type === "hostname") renderHostname(result);
      else renderIp(result);
      bindChips();
    } catch (err) {
      output.hidden = true;
      emptyEl.hidden = false;
      showError(err.message || "The lookup could not be completed.");
    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", runResolve);

  return {};
})();
