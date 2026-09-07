/** One test triggered by hand, streamed as NDJSON — same shape as traceroute
 *  and the discovery scans: phase markers and progress arrive as events, the
 *  UI just reflects whatever the latest event says. Two providers
 *  (Cloudflare, M-Lab NDT7) speak the same event shape, so nothing here
 *  needs to know which one is running beyond the label on the server line. */
const speedtestUI = (() => {
  const providerSelect = document.getElementById("speedtest-provider");
  const runBtn = document.getElementById("btn-run-speedtest");
  const stopBtn = document.getElementById("btn-stop-speedtest");
  const progress = document.getElementById("speedtest-progress");
  const errorEl = document.getElementById("speedtest-error");
  const serverEl = document.getElementById("speedtest-server");
  const emptyEl = document.getElementById("speedtest-empty");
  const phasesEl = document.getElementById("speed-phases");
  const barWrap = document.getElementById("speed-bar-wrap");
  const barFill = document.getElementById("speed-bar-fill");
  const barLabel = document.getElementById("speed-bar-label");
  const resultsEl = document.getElementById("speedtest-results");

  const valPing = document.getElementById("val-ping");
  const valJitter = document.getElementById("val-jitter");
  const valDownload = document.getElementById("val-download");
  const valUpload = document.getElementById("val-upload");

  let controller = null;

  function setBusy(busy, label) {
    runBtn.disabled = busy;
    providerSelect.disabled = busy;
    progress.hidden = !busy;
    if (busy) progress.innerHTML = `<span class="spinner"></span> ${label}`;
    stopBtn.hidden = !busy;
  }

  function showError(message) {
    errorEl.textContent = message;
    errorEl.hidden = false;
  }

  function showServer(event) {
    const name = event.provider === "ndt7" ? "M-Lab (NDT7)" : "Cloudflare";
    const where = event.location ? ` — ${event.location}` : "";
    serverEl.textContent = `server: ${name}${where} (${event.host})`;
    serverEl.hidden = false;
  }

  function setPhase(phase) {
    for (const el of phasesEl.querySelectorAll(".speed-phase")) {
      const isCurrent = el.dataset.phase === phase;
      el.classList.toggle("active", isCurrent);
      if (isCurrent) el.classList.remove("done");
    }
  }

  function markPhaseDone(phase) {
    const el = phasesEl.querySelector(`.speed-phase[data-phase="${phase}"]`);
    if (el) {
      el.classList.remove("active");
      el.classList.add("done");
    }
  }

  function showBar(label, fraction) {
    barWrap.hidden = false;
    barFill.style.width = `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`;
    barLabel.textContent = label;
  }

  function hideBar() {
    barWrap.hidden = true;
    barFill.style.width = "0%";
  }

  function resetResults() {
    errorEl.hidden = true;
    serverEl.hidden = true;
    emptyEl.hidden = true;
    resultsEl.hidden = false;
    hideBar();
    for (const el of phasesEl.querySelectorAll(".speed-phase")) {
      el.classList.remove("active", "done");
    }
    valPing.textContent = "—";
    valJitter.textContent = "—";
    valDownload.textContent = "—";
    valUpload.textContent = "—";
  }

  function mb(bytes) {
    return (bytes / 1_000_000).toFixed(1);
  }

  // Live Mbps so far, shown under the progress bar while a transfer runs —
  // not just the final number once the stage finishes.
  function liveMbps(bytes, elapsedS) {
    return elapsedS > 0 ? (bytes * 8) / elapsedS / 1_000_000 : 0;
  }

  function progressLabel(verb, event) {
    const speed = liveMbps(event.bytes, event.elapsed_s).toFixed(1);
    if (event.total != null) {
      return `${verb}… ${mb(event.bytes)} / ${mb(event.total)} MB · ${speed} Mbps`;
    }
    return `${verb}… ${mb(event.bytes)} MB · ${speed} Mbps`;
  }

  function progressFraction(event) {
    if (event.total != null) return event.bytes / event.total;
    if (event.duration_s) return event.elapsed_s / event.duration_s;
    return 0;
  }

  async function runSpeedtest() {
    errorEl.hidden = true;
    resetResults();

    const provider = providerSelect.value;
    const onEvent = (event) => {
      switch (event.type) {
        case "server":
          showServer(event);
          break;
        case "phase":
          setPhase(event.phase);
          if (event.phase === "download") showBar("starting download…", 0);
          if (event.phase === "upload") showBar("starting upload…", 0);
          break;
        case "ping":
          valPing.textContent = `${event.ping_ms.toFixed(0)} ms`;
          valJitter.textContent = `${event.jitter_ms.toFixed(1)} ms`;
          markPhaseDone("ping");
          break;
        case "download_progress":
          showBar(progressLabel("downloading", event), progressFraction(event));
          break;
        case "download":
          valDownload.textContent = event.mbps != null ? `${event.mbps.toFixed(1)} Mbps` : "—";
          markPhaseDone("download");
          hideBar();
          break;
        case "upload_progress":
          showBar(progressLabel("uploading", event), progressFraction(event));
          break;
        case "upload":
          valUpload.textContent = event.mbps != null ? `${event.mbps.toFixed(1)} Mbps` : "—";
          markPhaseDone("upload");
          hideBar();
          break;
        case "error":
          showError(event.message);
          break;
      }
    };

    controller = new AbortController();
    setBusy(true, "testing…");
    try {
      await api.streamSpeedtest(provider, onEvent, controller.signal);
    } catch (err) {
      if (err.name === "AbortError") {
        notify.toast("Speed test stopped — keeping whatever was measured so far.", { tone: "warning", title: "Stopped" });
      } else {
        showError(err.message || "The speed test could not be completed.");
      }
    } finally {
      setBusy(false, undefined);
      hideBar();
      controller = null;
    }
  }

  runBtn.addEventListener("click", runSpeedtest);
  stopBtn.addEventListener("click", () => controller?.abort());

  return {};
})();
