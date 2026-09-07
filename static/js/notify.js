/** In-page replacements for window.alert/confirm and silent console logging —
 *  a toast stack for background failures, and a modal for yes/no decisions
 *  the user actually has to make. Both styled like the rest of the console UI. */
const notify = (() => {
  const stack = document.getElementById("toast-stack");

  const ICONS = { error: "bi-x-octagon", warning: "bi-exclamation-triangle" };

  function toast(message, { tone = "error", title = "" } = {}) {
    const el = document.createElement("div");
    el.className = `toast toast-${tone}`;
    el.innerHTML = `
      <i class="bi ${ICONS[tone] || ICONS.error} toast-icon"></i>
      <div class="toast-body">
        ${title ? `<div class="toast-title">${escapeHtml(title)}</div>` : ""}
        <div class="toast-msg">${escapeHtml(message)}</div>
      </div>
      <button type="button" class="icon-btn toast-close" aria-label="Dismiss"><i class="bi bi-x-lg"></i></button>
    `;

    const remove = () => {
      el.classList.add("toast-leave");
      el.addEventListener("animationend", () => el.remove(), { once: true });
    };
    el.querySelector(".toast-close").addEventListener("click", remove);
    const timer = setTimeout(remove, 6000);
    el.addEventListener("mouseenter", () => clearTimeout(timer));

    stack.appendChild(el);
  }

  /** Replaces window.confirm — resolves true/false, never blocks the thread. */
  function confirmDialog({ title = "confirm", message, danger = false, confirmLabel = "confirm" }) {
    return new Promise((resolve) => {
      const backdrop = document.createElement("div");
      backdrop.className = "modal-backdrop";
      backdrop.innerHTML = `
        <div class="modal confirm-modal">
          <div class="modal-header">
            <h2><span class="sigil">?</span> ${escapeHtml(title)}</h2>
          </div>
          <div class="modal-body">
            <p class="confirm-message">${escapeHtml(message)}</p>
          </div>
          <div class="modal-actions">
            <div class="modal-actions-right">
              <button type="button" class="btn btn-ghost confirm-cancel">cancel</button>
              <button type="button" class="btn ${danger ? "btn-danger" : "btn-primary"} confirm-ok">${escapeHtml(
        confirmLabel
      )}</button>
            </div>
          </div>
        </div>
      `;

      const settle = (result) => {
        document.removeEventListener("keydown", onKeydown);
        backdrop.remove();
        resolve(result);
      };
      const onKeydown = (e) => {
        if (e.key === "Escape") settle(false);
        if (e.key === "Enter") settle(true);
      };

      backdrop.querySelector(".confirm-cancel").addEventListener("click", () => settle(false));
      backdrop.querySelector(".confirm-ok").addEventListener("click", () => settle(true));
      backdrop.addEventListener("click", (e) => {
        if (e.target === backdrop) settle(false);
      });
      document.addEventListener("keydown", onKeydown);

      document.body.appendChild(backdrop);
      backdrop.querySelector(".confirm-ok").focus();
    });
  }

  function escapeHtml(v) {
    return String(v).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[c]);
  }

  return { toast, confirm: confirmDialog };
})();
