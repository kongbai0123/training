import { appState, t } from "../state.js";
import { eventBus } from "../event_bus.js";
import { setText, qs, escapeHtml } from "../utils.js";
import { apiFetch } from "../api.js";

export function initEvaluation() {
  eventBus.on("language-changed", () => renderEvaluationPage());
}

export async function renderEvaluationPage() {
  if (!appState.currentProjectId) {
    setText("#eval-map50", "--");
    setText("#eval-iou", "--");
    setText("#eval-precision", "--");
    setText("#eval-recall", "--");
    qs("#evaluation-plots-grid")?.remove();
    return;
  }

  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/evaluation`);
    const metrics = data.metrics || {};
    
    setText("#eval-map50", data.has_metrics ? Number(metrics.map50 || 0).toFixed(3) : "--");
    setText("#eval-iou", data.has_metrics ? Number(metrics.map50_95 || 0).toFixed(3) : "--");
    setText("#eval-precision", data.has_metrics ? Number(metrics.precision || 0).toFixed(3) : "--");
    setText("#eval-recall", data.has_metrics ? Number(metrics.recall || 0).toFixed(3) : "--");

    let plotsGrid = qs("#evaluation-plots-grid");
    if (!plotsGrid) {
      plotsGrid = document.createElement("div");
      plotsGrid.id = "evaluation-plots-grid";
      plotsGrid.style.display = "grid";
      plotsGrid.style.gridTemplateColumns = "repeat(auto-fit, minmax(300px, 1fr))";
      plotsGrid.style.gap = "20px";
      plotsGrid.style.marginTop = "20px";
      
      const parent = qs("#page-evaluation");
      if (parent) {
        parent.appendChild(plotsGrid);
      }
    }

    if (data.has_metrics && data.plots && data.plots.length > 0) {
      plotsGrid.innerHTML = data.plots.map(plot => `
        <div class="plot-card" style="background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; display: flex; flex-direction: column; gap: 12px;">
          <h3 style="margin: 0; font-size: 0.92rem; color: var(--text-soft); text-transform: capitalize;">${escapeHtml(plot.replace('.png', '').replace('_', ' '))}</h3>
          <div style="background: var(--bg-preview); padding: 8px; border-radius: var(--radius); display: flex; justify-content: center; align-items: center; min-height: 200px;">
            <img src="/api/projects/${encodeURIComponent(appState.currentProjectId)}/evaluation/plot/${encodeURIComponent(plot)}?t=${Date.now()}" alt="${escapeHtml(plot)}" style="max-width: 100%; max-height: 400px; object-fit: contain; border-radius: 4px;">
          </div>
        </div>
      `).join("");
    } else {
      plotsGrid.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 32px; text-align: center; color: var(--text-muted);">${escapeHtml(t("evaluation.empty"))}</div>`;
    }
  } catch (err) {
    console.error("Failed to load evaluation metrics:", err);
    setText("#eval-map50", "--");
    setText("#eval-iou", "--");
    setText("#eval-precision", "--");
    setText("#eval-recall", "--");
  }
}
