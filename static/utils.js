import { eventBus } from "./event_bus.js";

export function qs(selector) {
  return document.querySelector(selector);
}

export function qsa(selector) {
  return [...document.querySelectorAll(selector)];
}

export function setText(selector, value) {
  const el = qs(selector);
  if (el) el.textContent = value;
}

export function setHTML(selector, html) {
  const el = qs(selector);
  if (el) el.innerHTML = html;
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function showToast(message) {
  eventBus.emit("toast", message);
}

export function colorForLabel(label) {
  const palette = ["#2563eb", "#16a34a", "#dc2626", "#9333ea", "#ea580c", "#0891b2", "#be123c", "#4f46e5"];
  const text = String(label || "label");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  }
  return palette[hash % palette.length];
}

export async function copyText(text) {
  if (!text || text === "尚未載入專案") return;
  try {
    await navigator.clipboard.writeText(text);
    showToast("路徑已複製");
  } catch {
    showToast("無法使用剪貼簿，請手動複製路徑");
  }
}

export async function collectDroppedFiles(dataTransfer) {
  const items = [...(dataTransfer?.items || [])];
  if (!items.length) return [...(dataTransfer?.files || [])];

  const entries = items
    .map((item) => item.webkitGetAsEntry?.())
    .filter(Boolean);

  if (!entries.length) return [...(dataTransfer?.files || [])];

  const nestedFiles = await Promise.all(entries.map(readEntryFiles));
  return nestedFiles.flat();
}

function readEntryFiles(entry) {
  if (!entry) return Promise.resolve([]);
  if (entry.isFile) {
    return new Promise((resolve) => {
      entry.file((file) => resolve([file]), () => resolve([]));
    });
  }
  if (!entry.isDirectory) return Promise.resolve([]);

  const reader = entry.createReader();
  const allEntries = [];

  return new Promise((resolve) => {
    const readBatch = () => {
      reader.readEntries(async (entries) => {
        if (!entries.length) {
          const nested = await Promise.all(allEntries.map(readEntryFiles));
          resolve(nested.flat());
          return;
        }
        allEntries.push(...entries);
        readBatch();
      }, () => resolve([]));
    };
    readBatch();
  });
}
