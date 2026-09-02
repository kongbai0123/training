import { appState } from "../state.js";
import { qsa } from "../utils.js";

const PAGE_ALIASES = Object.freeze({
  "rag-workbench": "dashboard",
  "project-assistant": "dashboard",
  cnn: "training",
  "cnn-training": "training",
  rnn: "training",
  "rnn-training": "training",
  "tabular-model": "tabular",
  "tabular-training": "tabular",
  compare: "model-compare",
  "labelme-manager": "labelme",
});

const KNOWN_PAGES = new Set([
  "dashboard",
  "projects",
  "history",
  "dataset",
  "labelme",
  "split",
  "augmentation",
  "training",
  "tabular",
  "evaluation",
  "model-compare",
  "inference",
  "auto-labeling",
  "export",
  "settings",
  "model-guide",
]);

export function canonicalizePageId(pageId) {
  const requested = String(pageId || "dashboard").trim().toLowerCase();
  const canonical = PAGE_ALIASES[requested] || requested;
  return KNOWN_PAGES.has(canonical) ? canonical : "dashboard";
}

export function setActivePage(pageId) {
  appState.currentPage = canonicalizePageId(pageId);

  qsa(".sidebar-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === appState.currentPage);
  });

  qsa(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${appState.currentPage}`);
  });

  return appState.currentPage;
}
