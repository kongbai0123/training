import { eventBus } from "../event_bus.js";
import { qs } from "../utils.js";
import { createCircularProgress } from "./loading.js";
import { t } from "../state.js";

const AUTO_HIDE_MS = 4200;

let hudEl = null;
let ring = null;
let activeJobId = null;
const jobs = new Map();
const hideTimers = new Map();

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
        <span class="global-progress-meta"><span id="global-progress-count" hidden></span><span id="global-progress-percent">0%</span></span>
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
  const existingTimer = hideTimers.get(data.jobId);
  if (existingTimer) window.clearTimeout(existingTimer);
  hideTimers.delete(data.jobId);
  jobs.set(data.jobId, { ...data, updatedAt: Date.now() });
  activeJobId = data.jobId;
  renderProgress(data, el);
}

function renderProgress(data, el = ensureHud()) {
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
  const activeCount = Array.from(jobs.values()).filter((job) => job.status === "running").length;
  const count = qs("#global-progress-count");
  if (count) {
    count.hidden = activeCount <= 1;
    count.textContent = activeCount > 1 ? t("task.common.count", { count: activeCount }) : "";
  }
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
  const previous = hideTimers.get(jobId);
  if (previous) window.clearTimeout(previous);
  const timer = window.setTimeout(() => {
    hideTimers.delete(jobId);
    jobs.delete(jobId);
    if (jobId && activeJobId && jobId !== activeJobId) return;
    const next = Array.from(jobs.values()).sort((a, b) => b.updatedAt - a.updatedAt)[0];
    if (next) {
      activeJobId = next.jobId;
      renderProgress(next);
      return;
    }
    hudEl?.classList.add("hidden");
    activeJobId = null;
  }, AUTO_HIDE_MS);
  hideTimers.set(jobId, timer);
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
