const targetsUI = (() => {
  const grid = document.getElementById("targets-grid");
  const emptyState = document.getElementById("empty-state");

  const modal = document.getElementById("target-modal");
  const modalTitle = document.getElementById("modal-title");
  const form = document.getElementById("target-form");
  const formError = document.getElementById("form-error");

  const fId = document.getElementById("f-id");
  const fName = document.getElementById("f-name");
  const fHost = document.getElementById("f-host");
  const fMethod = document.getElementById("f-method");
  const fMethodDesc = document.getElementById("f-method-desc");
  const fTcpPort = document.getElementById("f-tcp-port");
  const fHttpScheme = document.getElementById("f-http-scheme");
  const fHttpPath = document.getElementById("f-http-path");
  const fInterval = document.getElementById("f-interval");
  const fIntervalValue = document.getElementById("f-interval-value");
  const fIntervalMin = document.getElementById("f-interval-min");
  const fIntervalMax = document.getElementById("f-interval-max");
  const fEnabled = document.getElementById("f-enabled");
  const btnDelete = document.getElementById("btn-delete-target");

  const tcpFields = document.getElementById("f-tcp-fields");
  const httpFields = document.getElementById("f-http-fields");

  const METHOD_DESC = {
    ping: "Sends an ICMP echo request and waits for the reply. Cheapest check, but plenty of healthy hosts and firewalls drop ICMP entirely.",
    tcp: "Opens a TCP connection to one port and closes it. Proves something is actually listening on that port, not just that the host answers.",
    http: "Issues an HTTP request and waits for a response. The only method that tells you the web service itself is serving, not merely that the box is up.",
    dns: "Resolves the hostname to an address. Tests your resolver rather than the host &mdash; useful for catching DNS outages on their own.",
  };

  let limits = { interval_min_s: 1, interval_max_s: 60, default_interval_s: 5, buffer_size: 60 };
  let statusInfo = new Map(); // check code -> { label, description }
  const cards = new Map();

  // Must match --beat-period in css/style.css.
  const BEAT_MS = 2400;

  let armedEl = null;   // card whose grip is held down, so a drag may begin
  let dragEl = null;    // card currently being dragged
  let orderBeforeDrag = [];

  /** A negative animation-delay that starts every dot at the same point in the
   *  beat, so cards created minutes apart still pulse in unison. The rate never
   *  depends on the monitor's polling interval. */
  function beatPhase() {
    return `${(-(performance.now() % BEAT_MS) / 1000).toFixed(3)}s`;
  }

  function esc(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);
  }

  function init(newLimits, statusCodes) {
    limits = newLimits;
    statusInfo = new Map((statusCodes || []).map((s) => [s.code, s]));
    fInterval.min = limits.interval_min_s;
    fInterval.max = limits.interval_max_s;
    fInterval.value = limits.default_interval_s;
    fIntervalValue.textContent = limits.default_interval_s;
    fIntervalMin.textContent = `${limits.interval_min_s}s`;
    fIntervalMax.textContent = `${limits.interval_max_s}s`;
    charts.setBufferSize(limits.buffer_size);
  }

  function updateEmptyState() {
    emptyState.hidden = cards.size > 0;
  }

  function methodLabel(method) {
    return { ping: "icmp", tcp: "tcp", http: "http", dns: "dns" }[method] || method;
  }

  function targetSummary(target) {
    const what = {
      ping: `ICMP echo to ${target.host}`,
      tcp: `TCP connect to ${target.host}:${target.tcp_port ?? "?"}`,
      http: `${(target.http_scheme || "https").toUpperCase()} request to ${target.host}${target.http_path || "/"}`,
      dns: `DNS resolution of ${target.host}`,
    }[target.method];
    const cadence = target.enabled ? `every ${target.interval_s}s` : "polling stopped (monitor disabled)";
    return `${what}, ${cadence}`;
  }

  function statusClassFor(target, lastResult) {
    if (!target.enabled) return "unknown";
    if (!lastResult) return "unknown";
    return lastResult.success ? "up" : "down";
  }

  function statusTitle(status) {
    return {
      up: "Up — the most recent check succeeded",
      down: "Down — the most recent check failed",
      unknown: "Idle — monitor disabled, or no check has run yet",
    }[status];
  }

  function uptimePercent(ratio) {
    return ratio === null || ratio === undefined ? null : Math.round(ratio * 100);
  }

  /** The named reason a check failed, with the vocabulary's explanation as tooltip. */
  function resultLine(result) {
    if (!result) {
      return { html: '<span class="result-code idle">awaiting first check</span>', title: "" };
    }
    const info = statusInfo.get(result.code);
    const label = info ? info.label : result.label || result.code || "unknown";
    const tone = result.success ? "ok" : "fail";
    const detail = result.detail && result.detail !== label ? result.detail : "";
    return {
      html:
        `<span class="result-code ${tone}">${esc(label)}</span>` +
        (detail ? `<span class="result-detail">${esc(detail)}</span>` : ""),
      title: info ? `${info.label} — ${info.description}${detail ? `\n\nReported: ${detail}` : ""}` : detail,
    };
  }

  function latencyText(result) {
    if (!result || result.latency_ms === null || result.latency_ms === undefined) return "—";
    return `${Math.round(result.latency_ms)} ms`;
  }

  function buildCard(targetId, target, buffer, uptimeRatio) {
    const el = document.createElement("div");
    el.className = "target-card enter";
    el.dataset.id = targetId;
    el.draggable = false; // only draggable while the grip is actively held — see wireDrag()

    const lastResult = buffer.length ? buffer[buffer.length - 1] : null;
    const status = statusClassFor(target, lastResult);
    const pct = uptimePercent(uptimeRatio);
    const line = resultLine(target.enabled ? lastResult : null);

    el.innerHTML = `
      <div class="target-card-head">
        <div class="target-status">
          <span class="drag-handle" title="Drag to reorder"><i class="bi bi-grip-vertical"></i></span>
          <span class="status-dot ${status}" style="--beat-phase:${beatPhase()}" title="${esc(statusTitle(status))}"><span class="dot-core"></span></span>
          <div class="target-ident">
            <div class="target-name" title="Monitor name">${esc(target.name)}</div>
            <div class="target-host" title="Host being checked">${esc(target.host)}</div>
          </div>
        </div>
        <div class="target-card-actions">
          <button class="icon-btn btn-edit" aria-label="Edit"
                  title="Edit or delete this monitor"><i class="bi bi-pencil"></i></button>
        </div>
      </div>

      <div class="target-meta">
        <span class="badge ${target.enabled ? "" : "disabled"}" title="${esc(targetSummary(target))}">${esc(
      methodLabel(target.method)
    )} &middot; ${target.interval_s}s${target.enabled ? "" : " &middot; off"}</span>
        <span class="latency-text" title="Round-trip time of the most recent check">${latencyText(
          lastResult
        )}</span>
      </div>

      <div class="result-line" title="${esc(line.title)}">${line.html}</div>

      <div class="metric-row" title="Share of the last ${limits.buffer_size} checks that succeeded. Resets when the server restarts.">
        <span>uptime &middot; last ${limits.buffer_size} checks</span>
        <span class="uptime-value">${pct === null ? "no data" : `${pct}%`}</span>
      </div>
      <div class="uptime-bar-track"><div class="uptime-bar-fill" style="width:${pct ?? 0}%"></div></div>

      <div class="chart-wrap"><canvas></canvas></div>
      <div class="chart-caption">latency in ms, oldest &rarr; newest. Gaps are checks that never answered.</div>
    `;

    el.querySelector(".btn-edit").addEventListener("click", () => openEditModal(targetId));
    el.addEventListener("animationend", (e) => {
      if (e.animationName === "card-enter") el.classList.remove("enter");
    });
    wireDrag(el);

    grid.appendChild(el);
    charts.createChartFor(targetId, el.querySelector("canvas"), buffer);

    cards.set(targetId, {
      el,
      dot: el.querySelector(".status-dot"),
      latencyText: el.querySelector(".latency-text"),
      resultLine: el.querySelector(".result-line"),
      uptimeFill: el.querySelector(".uptime-bar-fill"),
      uptimeValue: el.querySelector(".uptime-value"),
      badge: el.querySelector(".badge"),
      target,
    });
    setStatus(targetId, status);
    updateEmptyState();
  }

  /** Drag-to-reorder for one card. The card is made draggable only for the
   *  duration of a mousedown on its grip, so dragging never fights with the
   *  chart canvas, text selection, or the edit button. */
  function wireDrag(el) {
    const handle = el.querySelector(".drag-handle");

    handle.addEventListener("mousedown", () => {
      armedEl = el;
      el.draggable = true;
    });
    // If the mouse comes up without a drag ever starting (a click, or a
    // press-and-release on the handle), disarm so a later unrelated drag
    // (e.g. text selection) can't accidentally move the card.
    document.addEventListener("mouseup", () => {
      if (armedEl && armedEl !== dragEl) armedEl.draggable = false;
      armedEl = null;
    });

    el.addEventListener("dragstart", (e) => {
      if (armedEl !== el) {
        e.preventDefault();
        return;
      }
      dragEl = el;
      orderBeforeDrag = [...grid.children].map((c) => c.dataset.id);
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", el.dataset.id);
      grid.classList.add("reordering");
      // Deferred so the browser finishes building the drag image before the
      // card visually drops out — otherwise the ghost image is blank.
      requestAnimationFrame(() => el.classList.add("dragging"));
    });

    el.addEventListener("dragover", (e) => {
      if (!dragEl || dragEl === el) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";

      const rect = el.getBoundingClientRect();
      const before = e.clientX < rect.left + rect.width / 2;
      grid.insertBefore(dragEl, before ? el : el.nextSibling);
    });

    el.addEventListener("dragend", () => {
      el.draggable = false;
      el.classList.remove("dragging");
      grid.classList.remove("reordering");
      if (dragEl !== el) return; // dragend fires on the source card only
      dragEl = null;

      const order = [...grid.children].map((c) => c.dataset.id);
      if (order.join() !== orderBeforeDrag.join()) persistOrder(order);
    });
  }

  /** Push the current grid order to the backend. On failure, put the grid back
   *  the way it was — silently retrying a drag is more confusing than leaving
   *  the user to try again. */
  async function persistOrder(order) {
    try {
      await api.reorderTargets(order);
    } catch (err) {
      console.error("Failed to save monitor order", err);
      orderBeforeDrag.forEach((id) => {
        const entry = cards.get(id);
        if (entry) grid.appendChild(entry.el);
      });
    }
  }

  /** Applied when another client reorders the grid; keeps this page in step
   *  without a full re-render (so charts and their live data aren't rebuilt). */
  function applyOrder(order) {
    if (dragEl) return; // don't fight a drag in progress on this client
    order.forEach((id) => {
      const entry = cards.get(id);
      if (entry) grid.appendChild(entry.el);
    });
  }

  function renderAll(snapshot) {
    grid.innerHTML = "";
    cards.clear();
    Object.entries(snapshot).forEach(([id, entry]) => {
      buildCard(id, entry.target, entry.buffer, entry.uptime_ratio);
    });
    updateEmptyState();
  }

  function upsertFromEvent(target) {
    const existing = cards.get(target.id);
    if (existing) {
      existing.target = target;
      existing.badge.innerHTML = `${esc(methodLabel(target.method))} &middot; ${target.interval_s}s${
        target.enabled ? "" : " &middot; off"
      }`;
      existing.badge.title = targetSummary(target);
      existing.badge.classList.toggle("disabled", !target.enabled);
      existing.el.querySelector(".target-name").textContent = target.name;
      existing.el.querySelector(".target-host").textContent = target.host;
      if (!target.enabled) {
        setStatus(target.id, "unknown");
        existing.resultLine.innerHTML = '<span class="result-code idle">polling stopped</span>';
        existing.resultLine.title = "This monitor is disabled, so no checks are running.";
      }
    } else {
      buildCard(target.id, target, [], null);
    }
  }

  function removeCard(targetId) {
    const entry = cards.get(targetId);
    if (!entry) return;
    charts.destroyChart(targetId);
    entry.el.remove();
    cards.delete(targetId);
    updateEmptyState();
  }

  function setStatus(targetId, status) {
    const entry = cards.get(targetId);
    if (!entry) return;
    entry.dot.className = `status-dot ${status}`;
    entry.dot.title = statusTitle(status);
    entry.el.classList.remove("is-up", "is-down", "is-unknown");
    entry.el.classList.add(`is-${status}`);
  }

  function applyCheckResult(targetId, result, uptimeRatio) {
    const entry = cards.get(targetId);
    if (!entry) return;

    const status = entry.target.enabled ? (result.success ? "up" : "down") : "unknown";
    setStatus(targetId, status);

    entry.latencyText.textContent = latencyText(result);
    entry.latencyText.classList.toggle("na", result.latency_ms === null || result.latency_ms === undefined);

    const line = resultLine(result);
    entry.resultLine.innerHTML = line.html;
    entry.resultLine.title = line.title;

    const pct = uptimePercent(uptimeRatio);
    if (pct !== null) {
      entry.uptimeFill.style.width = `${pct}%`;
      entry.uptimeValue.textContent = `${pct}%`;
    }

    // One-shot ping ripple: restarted by hand so consecutive results each animate.
    entry.dot.classList.remove("ping");
    void entry.dot.offsetWidth;
    entry.dot.classList.add("ping");

    entry.latencyText.classList.remove("flash");
    void entry.latencyText.offsetWidth;
    entry.latencyText.classList.add("flash");

    charts.pushResult(targetId, result);
  }

  function resetForm() {
    form.reset();
    fId.value = "";
    fInterval.value = limits.default_interval_s;
    fIntervalValue.textContent = limits.default_interval_s;
    formError.hidden = true;
    toggleMethodFields();
  }

  function toggleMethodFields() {
    tcpFields.hidden = fMethod.value !== "tcp";
    httpFields.hidden = fMethod.value !== "http";
    fMethodDesc.innerHTML = METHOD_DESC[fMethod.value] || "";
  }

  function openAddModal() {
    resetForm();
    modalTitle.innerHTML = '<span class="sigil">$</span> add monitor';
    btnDelete.hidden = true;
    modal.hidden = false;
    fHost.focus();
  }

  function openEditModal(targetId) {
    const entry = cards.get(targetId);
    if (!entry) return;
    const t = entry.target;

    resetForm();
    modalTitle.innerHTML = '<span class="sigil">$</span> edit monitor';
    fId.value = t.id;
    // A name that only mirrors the host was never typed by hand — leave the field
    // blank so it keeps tracking the host if the host is edited.
    fName.value = t.name === t.host ? "" : t.name;
    fHost.value = t.host;
    fMethod.value = t.method;
    fTcpPort.value = t.tcp_port ?? "";
    fHttpScheme.value = t.http_scheme ?? "https";
    fHttpPath.value = t.http_path ?? "";
    fInterval.value = t.interval_s;
    fIntervalValue.textContent = t.interval_s;
    fEnabled.checked = t.enabled;
    toggleMethodFields();

    btnDelete.hidden = false;
    modal.hidden = false;
    fHost.focus();
  }

  function closeModal() {
    modal.hidden = true;
  }

  function showFormError(message) {
    formError.textContent = message;
    formError.hidden = false;
  }

  fMethod.addEventListener("change", toggleMethodFields);
  fInterval.addEventListener("input", () => {
    fIntervalValue.textContent = fInterval.value;
  });
  fHost.addEventListener("input", () => {
    fName.placeholder = fHost.value.trim() ? `defaults to ${fHost.value.trim()}` : "defaults to the host";
  });

  document.getElementById("btn-add-target").addEventListener("click", openAddModal);
  document.getElementById("btn-close-modal").addEventListener("click", closeModal);
  document.getElementById("btn-cancel-modal").addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    formError.hidden = true;

    const host = fHost.value.trim();
    const payload = {
      // An unnamed monitor is labelled by the host it points at.
      name: fName.value.trim() || host,
      host,
      method: fMethod.value,
      interval_s: Number(fInterval.value),
      enabled: fEnabled.checked,
      tcp_port: fMethod.value === "tcp" ? Number(fTcpPort.value) || null : null,
      http_scheme: fMethod.value === "http" ? fHttpScheme.value : null,
      http_path: fMethod.value === "http" ? fHttpPath.value.trim() || "/" : null,
    };

    if (!payload.host) {
      showFormError("Host is required — enter an IP address or domain name.");
      return;
    }

    if (payload.method === "tcp" && !payload.tcp_port) {
      showFormError("TCP port is required for TCP checks.");
      return;
    }

    try {
      if (fId.value) {
        await api.updateTarget(fId.value, payload);
      } else {
        await api.createTarget(payload);
      }
      closeModal();
    } catch (err) {
      showFormError(err.message);
    }
  });

  btnDelete.addEventListener("click", async () => {
    if (!fId.value) return;
    if (!confirm("Delete this monitor? Its latency history goes with it.")) return;
    try {
      await api.deleteTarget(fId.value);
      closeModal();
    } catch (err) {
      showFormError(err.message);
    }
  });

  toggleMethodFields();

  return { init, renderAll, upsertFromEvent, removeCard, applyCheckResult, applyOrder };
})();
