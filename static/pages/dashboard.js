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
  setHTML("#dashboard-kpis", "");
  renderControlCards(status);
  renderRecentProjects(appState.projects);
  renderActivity(status);
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
      badge: "Ready",
      badgeClass: "success",
      desc: "管理 LabelMe JSON 工作流、同步標註進度並檢查錯誤。",
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
      desc: "設定物理擴充並預覽結果，輸出不污染原始資料。",
      stats: [["Requires", "Split"], ["Target", "Train"]],
      progress: status.splitComplete ? 60 : 0,
      actions: [button("Configure", "augmentation", "primary"), button("Preview", "augmentation", "secondary")],
    },
    {
      icon: "fa-microchip",
      title: "Training",
      badge: status.trainReady ? "Ready" : "Not ready",
      badgeClass: status.trainReady ? "success" : "danger",
      desc: "設定模型與啟動訓練；不符合條件時只鎖定危險操作。",
      stats: [["Status", status.trainingLabel], ["Blockers", status.blockers.length]],
      progress: status.trainReady ? 100 : 25,
      actions: [button("Configure", "training", "primary"), disabledButton("Start Training")],
    },
    {
      icon: "fa-chart-line",
      title: "Evaluation",
      badge: status.bestModelExists ? "Available" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      desc: "查看 mAP、IoU、failure cases 與模型品質。",
      stats: [["mAP", "--"], ["IoU", "--"]],
      progress: status.bestModelExists ? 100 : 0,
      actions: [button("View Evaluation", "evaluation", "primary")],
    },
    {
      icon: "fa-file-export",
      title: "Export",
      badge: status.bestModelExists ? "Exportable" : "No model",
      badgeClass: status.bestModelExists ? "success" : "warning",
      desc: "匯出 PT、ONNX 與訓練報告，供部署或交付使用。",
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
  eventBus.emit("render-recent-projects-list", (projects || []).slice(0, 3));
}

function renderActivity(status) {
  const items = [];
  if (!status.hasProject) {
    items.push("尚未載入專案。請使用 New Project 建立專案，或從 Browse History 開啟既有專案。");
  } else if (!status.hasDataset) {
    items.push("專案已載入，但尚未匯入資料。下一步建議前往 Dataset 匯入圖片或影片。");
  } else if (!status.splitComplete) {
    items.push("資料已匯入。下一步建議同步標註並建立 Train / Val / Test。");
  } else if (!status.trainReady) {
    items.push("Split 已建立，但訓練條件尚未完成。請檢查 Training 頁面的 blockers。");
  } else {
    items.push("專案已接近可訓練狀態。可前往 Training 設定模型並開始訓練。");
  }

  setHTML("#recent-activity-list", items.map((item) => `<div class="activity-item">${escapeHtml(item)}</div>`).join(""));
}
