import { appState } from "../state.js";
import { qsa } from "../utils.js";

export function setActivePage(pageId) {
  appState.currentPage = pageId || "dashboard";

  qsa(".sidebar-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === appState.currentPage);
  });

  qsa(".page").forEach((page) => {
    page.classList.toggle("active", page.id === `page-${appState.currentPage}`);
  });

  return appState.currentPage;
}
