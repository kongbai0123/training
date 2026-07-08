import { eventBus } from "../event_bus.js";

const staleResources = new Map();
const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function markResourceStale(id, { label = id, message = "", action = "Refresh project" } = {}) {
  if (!id) return;
  staleResources.set(id, {
    id,
    label,
    message: message || `${label} may have changed.`,
    action,
    updatedAt: new Date().toISOString()
  });
  eventBus.emit("resource-freshness-changed", getStaleResources());
  eventBus.emit("state-changed");
}

export function markResourceFresh(id) {
  if (!staleResources.delete(id)) return;
  eventBus.emit("resource-freshness-changed", getStaleResources());
  eventBus.emit("state-changed");
}

export function markAllResourcesFresh() {
  if (!staleResources.size) return;
  staleResources.clear();
  eventBus.emit("resource-freshness-changed", []);
  eventBus.emit("state-changed");
}

export function getStaleResources() {
  return [...staleResources.values()];
}

export function markResourceStaleFromRequest(url, method = "GET") {
  const normalizedMethod = String(method || "GET").toUpperCase();
  if (!MUTATING_METHODS.has(normalizedMethod)) return;
  const path = String(url || "");
  if (!path.startsWith("/api/projects/")) return;
  markResourceStale("project", {
    label: "Project data",
    message: "Project data changed after a local API action. Refresh before making deployment decisions.",
    action: "Refresh project"
  });
}

export function initResourceFreshnessTracking() {
  eventBus.on("refresh-project", () => markAllResourcesFresh());
  eventBus.on("open-project", () => markAllResourcesFresh());
  eventBus.on("project-deleted", () => markAllResourcesFresh());
}
