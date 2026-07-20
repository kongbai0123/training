import { eventBus } from "./event_bus.js";
import { appState, t } from "./state.js";
import { markResourceStaleFromRequest } from "./core/resource_freshness.js";
import { beginApiTask } from "./core/task_progress.js";

const inflightReads = new Map();
const responseCache = new Map();

function requestKey(url, options, method) {
  const headers = Object.entries(options.headers || {})
    .map(([key, value]) => [String(key).toLowerCase(), String(value)])
    .sort(([left], [right]) => left.localeCompare(right));
  return JSON.stringify([method, String(url), headers]);
}

function clearResponseCache() {
  responseCache.clear();
}

export class VtsApiError extends Error {
  constructor({ code = "API_ERROR", message = "Request failed", details = {}, suggestion = "", retryable = false, fieldErrors = {}, severity = "error", status = 0 } = {}) {
    super(message);
    this.name = "VtsApiError";
    this.code = code;
    this.details = details;
    this.suggestion = suggestion;
    this.retryable = Boolean(retryable);
    this.fieldErrors = fieldErrors || {};
    this.severity = severity || "error";
    this.status = Number(status) || 0;
  }
}

export function normalizeApiErrorPayload(payload = {}, status = 0) {
  const root = payload?.detail?.error ? payload.detail : payload;
  const error = root?.error || {};
  const message = error.message || root?.message || payload?.detail || `HTTP ${status}`;
  return {
    code: error.code || root?.code || "API_ERROR",
    message: typeof message === "string" ? message : "Request failed",
    details: error.details ?? root?.details ?? {},
    suggestion: error.suggestion || root?.suggestion || "",
    retryable: Boolean(error.retryable ?? root?.retryable),
    fieldErrors: error.field_errors || root?.field_errors || {},
    severity: error.severity || root?.severity || "error",
    status: error.status || root?.status || status,
  };
}

export function formatApiErrorForToast(error) {
  if (error instanceof VtsApiError) {
    const parts = [error.message];
    if (error.code) parts.push(`Code: ${error.code}`);
    if (error.suggestion) parts.push(error.suggestion);
    return parts.join(" | ");
  }
  return error?.message || String(error || "Request failed");
}

async function buildApiError(res) {
  try {
    const data = await res.json();
    return new VtsApiError(normalizeApiErrorPayload(data, res.status));
  } catch {
    const detail = await res.text();
    return new VtsApiError({ code: "HTTP_ERROR", message: detail || `HTTP ${res.status}`, status: res.status });
  }
}

export function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const suppressToast = Boolean(options.suppressToast);
  const token = appState.bootstrap?.token;
  const extraHeaders = { ...(options.headers || {}) };
  const isRead = method === "GET" || method === "HEAD";
  const key = isRead ? requestKey(url, options, method) : "";
  const cacheTtlMs = Math.max(0, Number(options.responseCacheTtlMs) || 0);
  const cached = key ? responseCache.get(key) : null;
  if (cached && cacheTtlMs > 0 && cached.expiresAt > Date.now()) {
    return Promise.resolve(cached.payload);
  }
  if (key && options.dedupe !== false && inflightReads.has(key)) {
    return inflightReads.get(key);
  }

  const task = beginApiTask(url, options, method);
  const {
    suppressToast: _suppressToast,
    suppressProgress: _suppressProgress,
    taskProgress: _taskProgress,
    progressMode: _progressMode,
    dedupe: _dedupe,
    responseCacheTtlMs: _responseCacheTtlMs,
    ...fetchOptions
  } = options;

  if (token) {
    extraHeaders["X-VTS-Token"] = token;
  }

  const request = (async () => {
    try {
      const res = await fetch(url, {
        ...fetchOptions,
        method,
        headers: extraHeaders,
      });
      if (!res.ok) {
        throw await buildApiError(res);
      }
      markResourceStaleFromRequest(url, method);
      const contentType = res.headers.get("content-type") || "";
      const payload = await (contentType.includes("application/json") ? res.json() : res.text());
      if (key && cacheTtlMs > 0) {
        responseCache.set(key, { payload, expiresAt: Date.now() + cacheTtlMs });
      }
      if (!isRead) clearResponseCache();
      task?.complete();
      return payload;
    } catch (err) {
      task?.fail({ message: err?.message || "Request failed" });
      if (!suppressToast) {
        eventBus.emit("toast", err instanceof VtsApiError ? err : formatApiErrorForToast(err));
      }
      throw err;
    }
  })();

  if (key && options.dedupe !== false) {
    const trackedRequest = request.finally(() => {
      if (inflightReads.get(key) === trackedRequest) inflightReads.delete(key);
    });
    inflightReads.set(key, trackedRequest);
    return trackedRequest;
  }
  return request;
}

export async function apiFetchBlob(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const suppressToast = Boolean(options.suppressToast);
  const token = appState.bootstrap?.token;
  const extraHeaders = { ...(options.headers || {}) };
  const task = beginApiTask(url, options, method);
  const {
    suppressToast: _suppressToast,
    suppressProgress: _suppressProgress,
    taskProgress: _taskProgress,
    progressMode: _progressMode,
    dedupe: _dedupe,
    responseCacheTtlMs: _responseCacheTtlMs,
    ...fetchOptions
  } = options;

  if (token) {
    extraHeaders["X-VTS-Token"] = token;
  }

  try {
    const res = await fetch(url, {
      ...fetchOptions,
      method,
      headers: extraHeaders,
    });
    if (!res.ok) {
      throw await buildApiError(res);
    }
    markResourceStaleFromRequest(url, method);
    const payload = await res.blob();
    task?.complete();
    return payload;
  } catch (err) {
    task?.fail({ message: err?.message || "Request failed" });
    if (!suppressToast) {
      eventBus.emit("toast", err instanceof VtsApiError ? err : formatApiErrorForToast(err));
    }
    throw err;
  }
}

export function apiUpload(url, options = {}) {
  const method = String(options.method || "POST").toUpperCase();
  const suppressToast = Boolean(options.suppressToast);
  const token = appState.bootstrap?.token;
  const task = beginApiTask(url, {
    ...options,
    taskProgress: {
      title: tUpload("task.upload.title", "Uploading"),
      stage: tUpload("task.upload.transferring", "Transferring files."),
      caption: tUpload("task.upload.caption", "Upload"),
      ...(typeof options.taskProgress === "object" ? options.taskProgress : {}),
    },
  }, method);

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    if (token) xhr.setRequestHeader("X-VTS-Token", token);
    Object.entries(options.headers || {}).forEach(([key, value]) => xhr.setRequestHeader(key, value));

    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable || event.total <= 0) {
        task?.update({ indeterminate: true, message: tUpload("task.upload.transferring", "Transferring files.") });
        return;
      }
      const percent = Math.max(0, Math.min(100, (event.loaded * 100) / event.total));
      task?.update({
        percent,
        indeterminate: false,
        message: tUpload("task.upload.bytes", `Uploaded ${event.loaded} of ${event.total} bytes.`, {
          loaded: formatUploadBytes(event.loaded),
          total: formatUploadBytes(event.total),
        }),
      });
    });

    xhr.upload.addEventListener("load", () => {
      task?.update({
        percent: 100,
        indeterminate: true,
        message: tUpload("task.upload.processing", "Upload complete. The application is validating and processing files."),
      });
    });

    xhr.addEventListener("load", () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        const error = buildXhrApiError(xhr);
        task?.fail({ message: error.message });
        if (!suppressToast) eventBus.emit("toast", error);
        reject(error);
        return;
      }
      markResourceStaleFromRequest(url, method);
      clearResponseCache();
      const contentType = xhr.getResponseHeader("content-type") || "";
      let payload = xhr.responseText;
      if (contentType.includes("application/json")) {
        try { payload = JSON.parse(xhr.responseText || "null"); } catch { payload = null; }
      }
      task?.complete();
      resolve(payload);
    });

    const failTransport = () => {
      const error = new VtsApiError({ code: "NETWORK_ERROR", message: tUpload("task.upload.networkFailed", "Upload connection failed."), status: xhr.status || 0 });
      task?.fail({ message: error.message });
      if (!suppressToast) eventBus.emit("toast", error);
      reject(error);
    };
    xhr.addEventListener("error", failTransport);
    xhr.addEventListener("abort", () => {
      const error = new VtsApiError({ code: "UPLOAD_CANCELLED", message: tUpload("task.upload.cancelled", "Upload cancelled."), status: 0 });
      task?.cancel({ message: error.message });
      reject(error);
    });
    xhr.send(options.body || null);
  });
}

function buildXhrApiError(xhr) {
  try {
    const payload = JSON.parse(xhr.responseText || "{}");
    return new VtsApiError(normalizeApiErrorPayload(payload, xhr.status));
  } catch {
    return new VtsApiError({ code: "HTTP_ERROR", message: xhr.responseText || `HTTP ${xhr.status}`, status: xhr.status });
  }
}

function formatUploadBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function tUpload(key, fallback, params = {}) {
  const translated = t(key, params);
  if (translated && translated !== key) return translated;
  return Object.entries(params).reduce((text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), fallback);
}
