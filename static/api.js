import { eventBus } from "./event_bus.js";
import { appState } from "./state.js";

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
      let detail = "";
      try {
        const data = await res.json();
        detail = data.detail || JSON.stringify(data);
      } catch {
        detail = await res.text();
      }
      const error = new Error(detail || `HTTP ${res.status}`);
      error.status = res.status;
      error.detail = detail;
      throw error;
    }
    const contentType = res.headers.get("content-type") || "";
    return contentType.includes("application/json") ? res.json() : res.text();
  } catch (err) {
    if (!suppressToast) {
      eventBus.emit("toast", err.message);
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
      let detail = "";
      try {
        const data = await res.json();
        detail = data.detail || JSON.stringify(data);
      } catch {
        detail = await res.text();
      }
      const error = new Error(detail || `HTTP ${res.status}`);
      error.status = res.status;
      error.detail = detail;
      throw error;
    }
    return res.blob();
  } catch (err) {
    if (!suppressToast) {
      eventBus.emit("toast", err.message);
    }
    throw err;
  }
}
