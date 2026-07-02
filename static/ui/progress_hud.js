import { eventBus } from "../event_bus.js";
import { qs } from "../utils.js";
import { createCircularProgress } from "./loading.js";

const AUTO_HIDE_MS = 4200;

let hudEl = null;
let ring = null;
let hideTimer = null;
let activeJobId = null;

function ensureHud() {
  if (hudEl) return hudEl;
  hudEl = document.createElement("div");
  hudEl.id = "global-progress-hud";
  hudEl.className = "global-progress-hud hidden";
  hudEl.setAttribute("role", "status");
  hudEl.setAttribute("aria-live", "polite");
  hudEl.innerHTML = `
    <div class="global-progress-ring circular-progress compact" data-caption="Progress" data-size="86" data-radius="33"></div>
    <div class="global-progress-content">
      <div class="global-progress-header">
        <strong id="global-progress-title">Working</strong>
        <span id="global-progress-percent">0%</span>
      </div>
      <div class="global-progress-message" id="global-progress-message">Preparing...</div>
      <div class="global-progress-bar-bg">
        <div class="global-progress-bar-fill" id="global-progress-bar-fill"></div>
      </div>
    </div>
  `;
  document.body.appendChild(hudEl);
  ring = createCircularProgress(qs(".global-progress-ring"), 0, { caption: "Progress" });
  return hudEl;
}

function normalizeProgress(payload = {}) {
  const percent = Number(payload.percent);
  return {
    jobId: payload.jobId || "global",
    title: payload.title || "Working",
    message: payload.message || "",
    caption: payload.caption || "Progress",
    status: payload.status || "running",
    indeterminate: Boolean(payload.indeterminate),
    percent: Number.isFinite(percent) ? Math.max(0, Math.min(100, percent)) : 0
  };
}

function showProgress(payload) {
  const data = normalizeProgress(payload);
  const el = ensureHud();

  if (hideTimer) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }

  activeJobId = data.jobId;
  el.classList.remove("hidden", "is-complete", "is-failed");
  el.classList.toggle("is-complete", data.status === "completed");
  el.classList.toggle("is-failed", data.status === "failed");
  el.classList.toggle("is-pending", data.indeterminate);

  qs("#global-progress-title").textContent = data.title;
  qs("#global-progress-percent").textContent = data.indeterminate ? "..." : `${Math.round(data.percent)}%`;
  qs("#global-progress-message").textContent = data.message;
  qs("#global-progress-bar-fill").style.width = `${data.percent}%`;
  ring ||= createCircularProgress(qs(".global-progress-ring"), data.percent, { caption: data.caption });
  ring.setCaption(data.caption);
  ring.set(data.percent);
  const ringText = qs(".global-progress-ring .progress-ring__value-text");
  if (ringText && data.indeterminate) ringText.textContent = "...";
}

function completeProgress(payload = {}) {
  const data = normalizeProgress({ ...payload, status: payload.status || "completed", percent: payload.percent ?? 100 });
  showProgress(data);
  scheduleHide(data.jobId);
}

function failProgress(payload = {}) {
  const data = normalizeProgress({ ...payload, status: "failed", percent: payload.percent ?? 100 });
  showProgress(data);
  scheduleHide(data.jobId);
}

function scheduleHide(jobId) {
  if (hideTimer) clearTimeout(hideTimer);
  hideTimer = setTimeout(() => {
    if (jobId && activeJobId && jobId !== activeJobId) return;
    hudEl?.classList.add("hidden");
    activeJobId = null;
  }, AUTO_HIDE_MS);
}

export function initGlobalProgressHud() {
  ensureHud();
  eventBus.on("progress:update", showProgress);
  eventBus.on("progress:complete", completeProgress);
  eventBus.on("progress:failed", failProgress);
  eventBus.on("progress:hide", (payload = {}) => {
    const jobId = payload.jobId || activeJobId;
    scheduleHide(jobId);
  });
}

export function emitProgressUpdate({ jobId, title, message, percent, caption = "Progress", status = "running" }) {
  eventBus.emit("progress:update", {
    jobId,
    title,
    message: message || "",
    percent,
    caption,
    status
  });
}
