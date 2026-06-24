import { eventBus } from "./event_bus.js";
import { appState } from "./state.js";

export async function apiFetch(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const token = appState.bootstrap?.token;
  const extraHeaders = { ...(options.headers || {}) };

  if (token) {
    extraHeaders["X-VTS-Token"] = token;
  }

  try {
    const res = await fetch(url, {
      ...options,
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
      throw new Error(detail || `HTTP ${res.status}`);
    }
    const contentType = res.headers.get("content-type") || "";
    return contentType.includes("application/json") ? res.json() : res.text();
  } catch (err) {
    eventBus.emit("toast", err.message);
    throw err;
  }
}
