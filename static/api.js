import { eventBus } from "./event_bus.js";
import { appState } from "./state.js";
import { markResourceStaleFromRequest } from "./core/resource_freshness.js";

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

export async function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const suppressToast = Boolean(options.suppressToast);
  const token = appState.bootstrap?.token;
  const extraHeaders = { ...(options.headers || {}) };
  const { suppressToast: _suppressToast, ...fetchOptions } = options;

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
    const contentType = res.headers.get("content-type") || "";
    return contentType.includes("application/json") ? res.json() : res.text();
  } catch (err) {
    if (!suppressToast) {
      eventBus.emit("toast", err instanceof VtsApiError ? err : formatApiErrorForToast(err));
    }
    throw err;
  }
}

export async function apiFetchBlob(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const suppressToast = Boolean(options.suppressToast);
  const token = appState.bootstrap?.token;
  const extraHeaders = { ...(options.headers || {}) };
  const { suppressToast: _suppressToast, ...fetchOptions } = options;

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
    return res.blob();
  } catch (err) {
    if (!suppressToast) {
      eventBus.emit("toast", err instanceof VtsApiError ? err : formatApiErrorForToast(err));
    }
    throw err;
  }
}
