import { eventBus } from "./event_bus.js";

export async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
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
