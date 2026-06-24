import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { qs, setHTML, escapeHtml } from "../utils.js";

export function initDashboard() {
  qs("#btn-dashboard-refresh")?.addEventListener("click", () => {
    eventBus.emit("refresh-project");
  });
}

export function renderDashboard(status) {
  setHTML("#dashboard-alerts", "");
  renderKpis(status);
  renderControlCards(status);
  renderRecentProjects(appState.projects);
  renderActivity(status);
}

function renderKpis(status) {
  const items = [
    ["Project", status.projectName],
    ["Images", status.imageCount],
    ["LabelMe JSON", `${status.labelme.jsonCount}/${status.imageCount}`],
    ["Split", status.splitComplete ? "Ready" : "Not ready"],
  ];

  setHTML("#dashboard-kpis", items.map(([label, value]) => `
    <div class="metric-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join(""));
}

function renderControlCards(status) {
  const cards = [
    {
      icon: "fa-folder-tree",
      title: "Project",
      badge: status.hasProject ? "Loaded" : "No project",
      badgeClass: status.hasProject ? "success" : "warning",
      desc: "建立、開啟與管理視覺訓練專案。",
      stats: [["Task", status.taskType], ["Classes", status.classNames.length]],
      progress: status.hasProject ? 100 : 0,
      actions: [button("New Project", "projects", "primary"), button("Browse History", "history", "secondary")],
    },
    {
      icon: "fa-images",
      title: "Dataset",
      badge: status.hasDataset ? "Imported" : "No data",
      badgeClass: status.hasDataset ? "success" : "warning",
      desc: "管理圖片、影片抽幀與品質檢查。",
      stats: [["Images", status.imageCount], ["Health", appState.currentProject?.dataset_health?.score ?? "--"]],
      progress: status.hasDataset ? 100 : 0,
      actions: [button("Import Images", "dataset", "primary"), button("Quality Check", "dataset", "secondary")],
    },
    {
      icon: "fa-pen-nib",
      title: "LabelMe",
      badge: "Backend Connected",
      badgeClass: "success",
      desc: "管理 LabelMe JSON 工作流，取代舊版 Canvas bbox 標註主入口。",
      stats: [["JSON", status.labelme.jsonCount], ["Missing", status.labelme.missingJson]],
      progress: status.labelme.completionRate,
      actions: [button("Open Manager", "labelme", "primary"), button("Sync JSON", "labelme", "secondary")],
    },
    {
      icon: "fa-code-branch",
      title: "Split",
      badge: status.splitComplete ? "Ready" : "Not split",
      badgeClass: status.splitComplete ? "success" : "warning",
      desc: "建立 Train / Val / Test，避免資料外洩。",
      stats: [["Train", status.splitCounts.train], ["Val", status.splitCounts.val], ["Test", status.splitCounts.test]],
      progress: status.splitComplete ? 100 : 0,
      actions: [button("Configure Split", "split", "primary"), button("Run Split", "split", "secondary")],
    },
    {
      icon: "fa-wand-magic-sparkles",
      title: "Augmentation",
      badge: appState.currentProject?.augmentation_config ? "Configured" : "Not configured",
      badgeClass: appState.currentProject?.augmentation_config ? "info" : "warning",
      desc: "設定物理擴充，並以 Train split 為主要套用目標。",
      stats: [["Requires", "Split"], ["Target", "Train"]],
      progress: status.splitComplete ? 60 : 0,
      actions: [button("Configure", "augmentation", "primary"), button("Preview", "augmentation", "secondary")],
    },
    {
      icon: "fa-microchip",
      title: "Training",
      badge: status.trainReady ? "Ready" : "Not ready",
      badgeClass: status.trainReady ? "success" : "danger",
      desc: "設定模型訓練參數，並依 LabelMe、Split 狀態啟用安全操作。",
      stats: [["Status", status.trainingLabel], ["Blockers", status.blockers.length]],
      progress: status.trainReady ? 100 : 25,
      actions: [button("Configure", "training", "primary"), disabledButton("Start Training")],
    },
    {
      icon: "fa-chart-line",
      title: "Evaluation",
      badge: status.bestModelExists ? "Available" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      desc: "查看 mAP、IoU、failure cases 等模型評估資訊。",
      stats: [["mAP", "--"], ["IoU", "--"]],
      progress: status.bestModelExists ? 100 : 0,
      actions: [button("View Evaluation", "evaluation", "primary")],
    },
    {
      icon: "fa-file-export",
      title: "Export",
      badge: status.bestModelExists ? "Exportable" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      desc: "匯出 PT、ONNX、報告與部署需要的模型成果。",
      stats: [["ONNX", "Supported"], ["TensorRT", "Pending"]],
      progress: status.bestModelExists ? 100 : 0,
      actions: [button("Open Export", "export", "primary")],
    },
  ];

  setHTML("#control-cards", cards.map(renderControlCard).join(""));
}

function renderControlCard(card) {
  return `
    <article class="control-card">
      <div class="card-heading"><i class="fa-solid ${card.icon}"></i><h3>${escapeHtml(card.title)}</h3></div>
      <span class="badge badge-${card.badgeClass}">${escapeHtml(card.badge)}</span>
      <p>${escapeHtml(card.desc)}</p>
      <div>
        ${card.stats.map((item) => `<div class="card-stat"><span>${escapeHtml(item[0])}</span><strong>${escapeHtml(item[1])}</strong></div>`).join("")}
        <div class="progress-block" style="margin-top:10px">
          <div class="progress-track"><div class="progress-fill" style="width:${Number(card.progress) || 0}%"></div></div>
        </div>
      </div>
      <div class="card-actions">${card.actions.join("")}</div>
    </article>
  `;
}

function button(label, page, type) {
  return `<button class="btn btn-${type}" data-nav="${page}">${escapeHtml(label)}</button>`;
}

function disabledButton(label) {
  return `<button class="btn btn-disabled" disabled>${escapeHtml(label)}</button>`;
}

function renderRecentProjects(projects) {
  eventBus.emit("render-recent-projects-list", (projects || []).slice(0, 5));
}

function renderActivity(status) {
  const items = [];
  if (!status.hasProject) {
    items.push("尚未開啟專案。");
  } else if (!status.hasDataset) {
    items.push("目前專案尚未匯入資料。");
  } else {
    items.push(`目前專案：${status.projectName}`);
  }

  setHTML("#recent-activity-list", items.map((item) => `<div class="activity-item">${escapeHtml(item)}</div>`).join(""));
}
