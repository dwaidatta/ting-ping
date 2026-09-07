/** One scan triggered by hand, streamed as NDJSON — same shape as the
 *  discovery sweep/port scan in discovery.js: hops render as they arrive,
 *  keyed by hop number so a re-run replaces rather than appends. */
const tracerouteUI = (() => {
  const form = document.getElementById("traceroute-form");
  const hostInput = document.getElementById("t-host");
  const familySelect = document.getElementById("t-family");
  const maxHopsInput = document.getElementById("t-max-hops");
  const runBtn = document.getElementById("btn-run-traceroute");
  const stopBtn = document.getElementById("btn-stop-traceroute");
  const progress = document.getElementById("traceroute-progress");
  const errorEl = document.getElementById("traceroute-error");
  const emptyEl = document.getElementById("traceroute-empty");
  const summaryEl = document.getElementById("traceroute-summary");
  const table = document.getElementById("hop-table");
  const tableBody = document.getElementById("hop-table-body");

  // Same cancellation pattern as discovery.js: aborting the fetch closes the
  // connection, which the server's `finally` (see app/traceroute.py) treats
  // as a signal to kill the still-running subprocess.
  let controller = null;

  function esc(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);
  }

  function setBusy(busy, label) {
    runBtn.disabled = busy;
    progress.hidden = !busy;
    if (busy) progress.innerHTML = `<span class="spinner"></span> ${label}`;
    stopBtn.hidden = !busy;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function rttCells(rtts) {
    return rtts
      .map((r) => `<td class="hop-rtt${r == null ? " hop-timeout" : ""}">${r == null ? "*" : `${Math.round(r)} ms`}</td>`)
      .join("");
  }

  function hopRow(hop) {
    const reached = hop.reached ? " hop-reached" : "";
    const timedOut = hop.ip ? "" : " hop-timeout";
    return `
      <tr class="hop-row${reached}${timedOut}" data-hop="${hop.hop}">
        <td class="hop-num">${hop.hop}</td>
        <td class="hop-addr">${hop.ip ? esc(hop.ip) : "&mdash;"}</td>
        <td class="hop-host">${hop.hostname ? esc(hop.hostname) : hop.ip ? "unresolved" : "&mdash;"}</td>
        ${rttCells(hop.rtts_ms)}
      </tr>`;
  }

  function renderHop(hop) {
    emptyEl.hidden = true;
    table.hidden = false;
    const existing = tableBody.querySelector(`tr[data-hop="${hop.hop}"]`);
    if (existing) existing.outerHTML = hopRow(hop);
    else tableBody.insertAdjacentHTML("beforeend", hopRow(hop));
  }

  function resetResults() {
    tableBody.innerHTML = "";
    table.hidden = true;
    summaryEl.hidden = true;
    emptyEl.hidden = false;
  }

  function showSummary(host, reached) {
    summaryEl.hidden = false;
    summaryEl.textContent = reached
      ? `reached ${host}`
      : `did not reach ${host} within the configured hop limit`;
  }

  async function runTraceroute(e) {
    e.preventDefault();
    errorEl.hidden = true;

    const host = hostInput.value.trim();
    if (!host) {
      showError("Enter a hostname, IPv4, or IPv6 address to trace.");
      return;
    }
    const family = familySelect.value;
    const maxHops = maxHopsInput.value ? parseInt(maxHopsInput.value, 10) : undefined;

    resetResults();

    const onEvent = (event) => {
      if (event.type === "hop") {
        renderHop(event.hop);
      } else if (event.type === "done") {
        showSummary(host, event.reached);
      } else if (event.type === "error") {
        showError(event.message);
      }
    };

    controller = new AbortController();
    setBusy(true, "tracing…");
    try {
      await api.streamTraceroute(host, family, maxHops, onEvent, controller.signal);
    } catch (err) {
      if (err.name === "AbortError") {
        notify.toast("Trace stopped — keeping the hops found so far.", { tone: "warning", title: "Stopped" });
      } else {
        showError(err.message || "The trace could not be completed.");
      }
    } finally {
      setBusy(false, undefined);
      controller = null;
    }
  }

  form.addEventListener("submit", runTraceroute);
  stopBtn.addEventListener("click", () => controller?.abort());

  return {};
})();
