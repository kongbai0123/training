import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";

const DEFAULT_DELAY_MS = 500;
const COMPLETE_HIDE_MS = 4200;
const activeTasks = new Map();
let sequence = 0;
let lastActionButton = null;
let lastActionAt = 0;

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

function nextTaskId(prefix = "request") {
  sequence += 1;
  return `${prefix}-${Date.now()}-${sequence}`;
}

function cleanUrl(url = "") {
  return String(url).split("?")[0].toLowerCase();
}

function classifyRequest(url, method) {
  const path = cleanUrl(url);
  const isRead = method === "GET" || method === "HEAD";
  if (/train\/(start|stop|abort)|\/train$/.test(path)) return { kind: "training", title: t("task.training.title"), stage: t("task.training.preparing") };
  if (/export|report/.test(path)) return { kind: "export", title: t("task.export.title"), stage: t("task.export.preparing") };
  if (/inference|predict|test/.test(path)) return { kind: "inference", title: t("task.inference.title"), stage: t("task.inference.preparing") };
  if (/evaluation|compare|metrics/.test(path)) return { kind: "evaluation", title: t("task.evaluation.title"), stage: t("task.evaluation.loading") };
  if (/model.*(install|import)|models\/(install|import)/.test(path)) return { kind: "model", title: t("task.model.title"), stage: t("task.model.preparing") };
  if (/sync|quality-check|split/.test(path)) return { kind: "sync", title: t("task.sync.title"), stage: t("task.sync.processing") };
  if (/import|upload|dataset/.test(path) && !isRead) return { kind: "import", title: t("task.import.title"), stage: t("task.import.processing") };
  if (isRead) return { kind: "load", title: t("task.load.title"), stage: t("task.load.waiting") };
  return { kind: "operation", title: t("task.operation.title"), stage: t("task.operation.processing") };
}

function resolveActionButton(explicitButton, method) {
  if (explicitButton instanceof HTMLElement) return explicitButton.closest("button, [role='button']") || explicitButton;
  if (lastActionButton && (Date.now() - lastActionAt) < 1200 && document.contains(lastActionButton)) {
    if ((method === "GET" || method === "HEAD") && lastActionButton.matches("[data-page], [data-nav], .sidebar-item")) return null;
    return lastActionButton;
  }
  if (method === "GET" || method === "HEAD") return null;
  const active = document.activeElement;
  return active instanceof HTMLElement ? active.closest("button, [role='button']") : null;
}

function setButtonBusy(task, busy) {
  const button = task.button;
  if (!button) return;
  if (busy) {
    if (!task.buttonSnapshot) {
      task.buttonSnapshot = {
        disabled: Boolean(button.disabled),
        ariaBusy: button.getAttribute("aria-busy"),
        html: button.innerHTML,
      };
    }
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.classList.add("is-task-busy");
    if (!button.querySelector(".task-button-spinner")) {
      button.insertAdjacentHTML("afterbegin", '<span class="task-button-spinner" aria-hidden="true"></span>');
    }
    return;
  }
  if (!task.buttonSnapshot) return;
  button.innerHTML = task.buttonSnapshot.html;
  button.disabled = task.buttonSnapshot.disabled;
  if (task.buttonSnapshot.ariaBusy === null) button.removeAttribute("aria-busy");
  else button.setAttribute("aria-busy", task.buttonSnapshot.ariaBusy);
  button.classList.remove("is-task-busy");
}

function resolveInlineHost(task) {
  if (task.inlineHost instanceof HTMLElement) return task.inlineHost;
  const buttonHost = task.button?.closest(".control-card, .panel-section, .modal-content, .workflow-card");
  if (buttonHost) return buttonHost;
  return document.querySelector(".page.active .page-header, .page:not([hidden]) .page-header, main");
}

function ensureInline(task) {
  if (task.inlineEl?.isConnected) return task.inlineEl;
  const host = resolveInlineHost(task);
  if (!host) return null;
  const el = document.createElement("div");
  el.className = "task-progress-inline is-running";
  el.dataset.taskId = task.id;
  el.setAttribute("role", "status");
  el.setAttribute("aria-live", "polite");
  el.innerHTML = `
    <div class="task-progress-inline__header">
      <strong class="task-progress-inline__title"></strong>
      <span class="task-progress-inline__percent">...</span>
    </div>
    <div class="task-progress-inline__track"><span class="task-progress-inline__fill"></span></div>
    <div class="task-progress-inline__message"></div>
  `;
  if (host.matches(".page-header")) host.insertAdjacentElement("afterend", el);
  else host.appendChild(el);
  task.inlineEl = el;
  return el;
}

function renderInline(task) {
  const el = ensureInline(task);
  if (!el) return;
  el.className = `task-progress-inline is-${task.status}${task.indeterminate ? " is-indeterminate" : ""}`;
  el.querySelector(".task-progress-inline__title").textContent = task.title;
  el.querySelector(".task-progress-inline__percent").textContent = task.indeterminate ? "..." : `${Math.round(task.percent)}%`;
  el.querySelector(".task-progress-inline__fill").style.width = `${task.percent}%`;
  el.querySelector(".task-progress-inline__message").textContent = task.message || task.stage || "";
}

function emitGlobal(task, eventName = "progress:update") {
  eventBus.emit(eventName, {
    jobId: task.id,
    title: task.title,
    message: task.message || task.stage,
    percent: task.percent,
    caption: task.caption,
    status: task.status,
    indeterminate: task.indeterminate,
    kind: task.kind,
  });
}

function reveal(task) {
  if (task.visible || TERMINAL.has(task.status)) return;
  task.visible = true;
  renderInline(task);
  emitGlobal(task);
}

function finalize(task, status, payload = {}) {
  if (!task || TERMINAL.has(task.status)) return;
  window.clearTimeout(task.delayTimer);
  task.status = status;
  task.percent = status === "completed" ? 100 : Math.max(0, Math.min(100, Number(payload.percent ?? task.percent) || 0));
  task.indeterminate = false;
  task.message = payload.message || (status === "completed" ? t("task.common.completed") : t("task.common.failed"));
  setButtonBusy(task, false);
  if (task.visible) {
    renderInline(task);
    emitGlobal(task, status === "completed" ? "progress:complete" : "progress:failed");
    window.setTimeout(() => task.inlineEl?.remove(), COMPLETE_HIDE_MS);
  }
  activeTasks.delete(task.id);
}

export function beginTask(options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const profile = classifyRequest(options.url, method);
  const task = {
    id: options.jobId || nextTaskId(profile.kind),
    kind: options.kind || profile.kind,
    title: options.title || profile.title,
    stage: options.stage || profile.stage,
    message: options.message || options.stage || profile.stage,
    caption: options.caption || t("task.common.caption"),
    percent: Number(options.percent) || 0,
    indeterminate: options.indeterminate !== false,
    status: "running",
    visible: false,
    button: resolveActionButton(options.button, method),
    inlineHost: options.inlineHost || null,
    inlineEl: null,
    buttonSnapshot: null,
    delayTimer: null,
  };
  activeTasks.set(task.id, task);
  setButtonBusy(task, true);
  task.delayTimer = window.setTimeout(() => reveal(task), Number(options.delayMs ?? DEFAULT_DELAY_MS));

  return {
    id: task.id,
    show: () => reveal(task),
    update(payload = {}) {
      if (TERMINAL.has(task.status)) return;
      if (payload.title) task.title = payload.title;
      if (payload.stage) task.stage = payload.stage;
      if (payload.message) task.message = payload.message;
      if (payload.caption) task.caption = payload.caption;
      if (payload.percent !== undefined && Number.isFinite(Number(payload.percent))) {
        task.percent = Math.max(0, Math.min(100, Number(payload.percent)));
      }
      if (payload.indeterminate !== undefined) task.indeterminate = Boolean(payload.indeterminate);
      reveal(task);
      renderInline(task);
      emitGlobal(task);
    },
    complete: (payload = {}) => finalize(task, "completed", payload),
    fail: (payload = {}) => finalize(task, "failed", payload),
    cancel: (payload = {}) => finalize(task, "cancelled", payload),
  };
}

export function beginApiTask(url, options = {}, method = "GET") {
  if (options.suppressProgress || options.taskProgress === false) return null;
  const normalizedMethod = String(method || "GET").toUpperCase();
  const isBackgroundRead = (normalizedMethod === "GET" || normalizedMethod === "HEAD")
    && options.progressMode !== "foreground"
    && options.taskProgress !== true
    && typeof options.taskProgress !== "object";
  if (isBackgroundRead) return null;
  const custom = typeof options.taskProgress === "object" ? options.taskProgress : {};
  return beginTask({ ...custom, url, method });
}

export function initTaskProgressFramework() {
  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button, [role='button']") : null;
    if (!button) return;
    lastActionButton = button;
    lastActionAt = Date.now();
  }, true);
}

export function getActiveTasks() {
  return Array.from(activeTasks.values()).map((task) => ({
    id: task.id,
    kind: task.kind,
    status: task.status,
    percent: task.percent,
    indeterminate: task.indeterminate,
  }));
}

export function followServerTask(jobId, options = {}) {
  const controller = options.controller || beginTask({
    jobId,
    kind: options.kind || "operation",
    title: options.title || t("task.operation.title"),
    stage: t("task.phase.queued"),
    method: "POST",
    button: options.button,
    inlineHost: options.inlineHost,
  });
  const terminal = new Set(["completed", "failed", "cancelled"]);
  let settled = false;
  let socket = null;
  let pollTimer = null;

  return new Promise((resolve, reject) => {
    const finish = (task) => {
      if (settled) return;
      const status = String(task?.status || "").toLowerCase();
      const phaseMessage = resolveServerPhaseMessage(task);
      const progress = Number(task?.progress);
      if (status === "completed") {
        settled = true;
        controller.complete({ message: phaseMessage || t("task.common.completed") });
        cleanup();
        resolve(task?.result);
        return;
      }
      if (status === "failed" || status === "cancelled") {
        settled = true;
        const message = task?.error || phaseMessage || t("task.common.failed");
        controller.fail({ message, percent: Number.isFinite(progress) ? progress : 0 });
        cleanup();
        reject(new Error(message));
        return;
      }
      controller.update({
        message: phaseMessage,
        percent: Number.isFinite(progress) ? progress : 0,
        indeterminate: Boolean(task?.indeterminate),
      });
    };

    const poll = async () => {
      if (settled) return;
      try {
        const headers = {};
        if (appState.bootstrap?.token) headers["X-VTS-Token"] = appState.bootstrap.token;
        const response = await fetch(`/api/tasks/${encodeURIComponent(jobId)}`, { headers, cache: "no-store" });
        if (!response.ok) throw new Error(`Task status HTTP ${response.status}`);
        const payload = await response.json();
        finish(payload);
        if (!settled && !terminal.has(String(payload?.status || "").toLowerCase())) {
          pollTimer = window.setTimeout(poll, 750);
        }
      } catch (error) {
        if (!settled) pollTimer = window.setTimeout(poll, 1500);
      }
    };

    const cleanup = () => {
      if (pollTimer) window.clearTimeout(pollTimer);
      if (socket && socket.readyState < WebSocket.CLOSING) socket.close();
    };

    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${window.location.host}/api/tasks/${encodeURIComponent(jobId)}/ws`);
      socket.addEventListener("message", (event) => {
        try { finish(JSON.parse(event.data)); } catch { /* status polling remains available */ }
      });
      socket.addEventListener("error", () => {
        if (!pollTimer && !settled) void poll();
      });
      socket.addEventListener("close", () => {
        if (!settled && !pollTimer) void poll();
      });
    } catch {
      void poll();
    }
  });
}

function resolveServerPhaseMessage(task = {}) {
  const phase = String(task.phase || "").toLowerCase();
  const key = `task.phase.${phase}`;
  const translated = t(key);
  const base = translated && translated !== key ? translated : (task.message || "");
  const current = Number(task.current || 0);
  const total = Number(task.total || 0);
  return total > 0 ? `${base} (${Math.min(current, total)}/${total})` : base;
}
