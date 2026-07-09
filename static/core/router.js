import { appState } from "../state.js";
import { qsa } from "../utils.js";

export function setActivePage(pageId) {
  const aliases = {
    "rag-workbench": "dashboard",
    "project-assistant": "dashboard",
  };
  appState.currentPage = aliases[pageId] || pageId || "dashboard";

  qsa(".sidebar-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === appState.currentPage);
  });

  qsa(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${appState.currentPage}`);
  });

  return appState.currentPage;
}
