import { eventBus } from "../event_bus.js";

const dirtyForms = new Map();

export function registerDirtyForm({ id, label, selector, save = null, reset = null } = {}) {
  if (!id || !selector) return;
  dirtyForms.set(id, {
    id,
    label: label || id,
    selector,
    dirty: false,
    save,
    reset
  });
}

export function markDirtyForm(id, dirty = true) {
  const record = dirtyForms.get(id);
  if (!record || record.dirty === Boolean(dirty)) return;
  record.dirty = Boolean(dirty);
  eventBus.emit("dirty-forms-changed", getDirtyFormSummaries());
  eventBus.emit("state-changed");
}

export function markAllFormsClean() {
  let changed = false;
  dirtyForms.forEach((record) => {
    if (record.dirty) {
      record.dirty = false;
      changed = true;
    }
  });
  if (changed) {
    eventBus.emit("dirty-forms-changed", getDirtyFormSummaries());
    eventBus.emit("state-changed");
  }
}

export function hasAnyDirtyForm() {
  return getDirtyFormSummaries().length > 0;
}

export function getDirtyFormSummaries() {
  return [...dirtyForms.values()]
    .filter((record) => record.dirty)
    .map(({ id, label, selector }) => ({ id, label, selector }));
}

export function initDirtyFormTracking() {
  registerDirtyForm({
    id: "training-config",
    label: "Training config",
    selector: "#form-training-config"
  });

  dirtyForms.forEach((record) => {
    const form = document.querySelector(record.selector);
    if (!form) return;
    form.addEventListener("input", () => markDirtyForm(record.id, true));
    form.addEventListener("change", () => markDirtyForm(record.id, true));
    form.addEventListener("submit", () => markDirtyForm(record.id, false));
  });

  window.addEventListener("beforeunload", (event) => {
    if (!hasAnyDirtyForm()) return;
    event.preventDefault();
    event.returnValue = "";
  });

  eventBus.on("refresh-project", () => markAllFormsClean());
  eventBus.on("project-deleted", () => markAllFormsClean());
}
