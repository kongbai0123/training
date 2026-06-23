import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, setText, setHTML, escapeHtml } from "../utils.js";

export function initTraining() {
  qs("#btn-start-train")?.addEventListener("click", async () => {
    const status = getProjectStatus(appState.currentProject);
    if (!status.trainReady) {
      eventBus.emit("toast", "目前尚未滿足訓練條件");
      return;
    }
    try {
      await apiFetch(`/api/projects/${appState.currentProjectId}/train/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: qs("#train-model").value,
          epochs: Number(qs("#train-epochs").value),
          batch_size: Number(qs("#train-batch").value),
          imgsz: Number(qs("#train-imgsz").value),
          lr0: Number(qs("#train-lr0").value),
          device: qs("#train-device").value
        })
      });
      startMonitorWebSocket();
      eventBus.emit("toast", "訓練已啟動");
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `啟動訓練失敗：${err.message}`);
    }
  });

  qs("#btn-stop-train")?.addEventListener("click", async () => {
    try {
      await apiFetch(`/api/projects/${appState.currentProjectId}/train/stop`, { method: "POST" });
      eventBus.emit("toast", "已送出停止訓練要求");
    } catch (err) {
      eventBus.emit("toast", `停止訓練失敗：${err.message}`);
    }
  });

  // 監聽全域事件以判斷是否需要重新建立 WebSocket 連線
  eventBus.on("check-training-websocket", () => {
    if (appState.trainingStatus?.status === "training") {
      startMonitorWebSocket();
    }
  });
}

export function renderTrainingMonitor() {
  const status = appState.trainingStatus || {};
  setText("#train-status-label", status.status || "Idle");
  setText("#train-progress-text", `Epoch ${status.epoch || 0} / ${status.total_epochs || 0}`);
  const hw = status.hardware || {};
  setText("#hw-cpu-val", hw.cpu_usage !== undefined ? `${hw.cpu_usage}%` : "--");
  setText("#hw-ram-val", hw.ram_used !== undefined ? `${hw.ram_used} / ${hw.ram_total} MB` : "--");
  const gpu = hw.gpu || {};
  setText("#hw-gpu-val", gpu.available ? `${gpu.usage}%` : "N/A");
  setText("#hw-vram-val", gpu.available ? `${gpu.vram_used} / ${gpu.vram_total} MB` : "N/A");
  const metrics = status.metrics || [];
  setHTML("#training-metrics-list", metrics.length ? metrics.slice(-8).reverse().map((item) => `
    <div class="activity-item">Epoch ${item.epoch}: loss ${Number(item.loss || 0).toFixed(4)}, mAP50 ${Number(item.map50 || 0).toFixed(3)}</div>
  `).join("") : `<div class="empty-state">尚無訓練 metrics。</div>`);
  
  const isTraining = status.status === "training";
  qs("#btn-stop-train")?.classList.toggle("hidden", !isTraining);
  const startBtn = qs("#btn-start-train");
  if (startBtn) {
    startBtn.disabled = isTraining;
  }
}

function startMonitorWebSocket() {
  if (!appState.currentProjectId) return;
  if (appState.wsConn) {
    if (appState.wsConn.readyState === WebSocket.OPEN || appState.wsConn.readyState === WebSocket.CONNECTING) {
      return;
    }
    try {
      appState.wsConn.close();
    } catch (e) {}
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  appState.wsConn = new WebSocket(`${protocol}//${window.location.host}/api/projects/${appState.currentProjectId}/monitor`);
  appState.wsConn.onmessage = (event) => {
    appState.trainingStatus = JSON.parse(event.data);
    renderTrainingMonitor();
    eventBus.emit("state-changed");
    if (appState.trainingStatus.status !== "training") {
      try {
        appState.wsConn.close();
      } catch (e) {}
    }
  };
  appState.wsConn.onclose = () => {
    appState.wsConn = null;
  };
  appState.wsConn.onerror = () => {
    eventBus.emit("toast", "Training monitor WebSocket 發生錯誤");
    appState.wsConn = null;
  };
}
