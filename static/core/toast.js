import { qs, escapeHtml } from "../utils.js";

export function showToast(payload) {
  const toast = qs("#toast");
  if (!toast) return;
  const message = typeof payload === "object" ? payload.message : payload;
  const code = typeof payload === "object" ? payload.code : "";
  const suggestion = typeof payload === "object" ? payload.suggestion : "";
  const severity = typeof payload === "object" ? payload.severity || "error" : "info";
  toast.className = `toast toast-${severity}`;
  toast.innerHTML = code || suggestion
    ? `<strong>${escapeHtml(message || "Request failed")}</strong>${code ? `<small>Code: ${escapeHtml(code)}</small>` : ""}${suggestion ? `<small>${escapeHtml(suggestion)}</small>` : ""}`
    : escapeHtml(message || "");
  toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toast.hidden = true;
  }, 3200);
}
