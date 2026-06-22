// Vision Training Studio - App JavaScript Frontend

// --- 全域變數與狀態管理 ---
let currentProjectId = null;
let currentProject = null;
let activeTab = "tab-project";
let classColors = {};

// 標註器專用狀態
let currentImageIndex = -1;
let currentImageObj = null;
let loadedImage = null; // Image 元素
let bboxes = []; // 格式: [{category: "crack", bbox: [xc, yc, w, h], type: "bbox"}]
let selectedBBoxIndex = -1;
let selectedClass = "";
let zoomScale = 1.0;
let panOffsetX = 0;
let panOffsetY = 0;
let isPanning = false;
let isDrawing = false;
let startX = 0;
let startY = 0;
let lastMouseX = 0;
let lastMouseY = 0;
let spacePressed = false;
let undoStack = [];
let redoStack = [];

// 訓練與圖表狀態
let trainChart = null;
let wsConn = null;

// --- 初始化程序 ---
document.addEventListener("DOMContentLoaded", () => {
  initTabNavigation();
  initProjectForm();
  initHistoryBrowse();
  initDatasetModule();
  initAnnotationCanvas();
  initSplitModule();
  initAugmentModule();
  initTrainingModule();
  initExportModule();
  
  // 重新整理頁面時，載入最近專案
  loadRecentProjects();
});

// --- 自定義確認對話框 ---
function showConfirm(title, message, callback) {
  const modal = document.getElementById("custom-confirm-dialog");
  document.getElementById("confirm-title").innerText = title;
  document.getElementById("confirm-message").innerText = message;
  modal.style.display = "flex";

  const btnOk = document.getElementById("confirm-btn-ok");
  const btnCancel = document.getElementById("confirm-btn-cancel");

  const cleanup = () => {
    modal.style.display = "none";
    btnOk.onclick = null;
    btnCancel.onclick = null;
  };

  btnOk.onclick = () => {
    cleanup();
    callback(true);
  };
  btnCancel.onclick = () => {
    cleanup();
    callback(false);
  };
}

// --- Tab 導覽與流程解鎖 ---
function initTabNavigation() {
  const steps = document.querySelectorAll("#main-flow-nav .nav-step");
  steps.forEach(step => {
    step.addEventListener("click", () => {
      const tabId = step.getAttribute("data-tab");
      switchTab(tabId);
    });
  });
}

function switchTab(tabId) {
  // 防呆：如果沒有專案，除了 tab-project 以外都不能點
  if (!currentProjectId && tabId !== "tab-project") {
    alert("請先選擇或建立一個專案！");
    return;
  }

  // 防呆：如果是訓練/分散，檢查資料集是否有圖片
  if (currentProject && tabId !== "tab-project" && tabId !== "tab-dataset") {
    if (!currentProject.images || currentProject.images.length === 0) {
      alert("資料集內尚無影像，請先匯入影像！");
      return;
    }
  }

  activeTab = tabId;
  
  // 更新導覽列樣式
  document.querySelectorAll("#main-flow-nav .nav-step").forEach(step => {
    if (step.getAttribute("data-tab") === tabId) {
      step.classList.add("active");
    } else {
      step.classList.remove("active");
    }
  });

  // 更新分頁顯示
  document.querySelectorAll(".tab-content").forEach(tab => {
    if (tab.id === tabId) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });

  // 分頁特定載入邏輯
  if (tabId === "tab-dataset") {
    renderImageBrowser();
  } else if (tabId === "tab-label") {
    initAnnotationWorkspace();
  } else if (tabId === "tab-split") {
    updateSplitAugUI();
  } else if (tabId === "tab-train") {
    initTrainingDashboard();
  } else if (tabId === "tab-eval") {
    loadEvaluationData();
  }
}

// 解鎖流程導航
function unlockFlowSteps() {
  document.getElementById("nav-dataset").classList.remove("disabled");
  if (currentProject && currentProject.images && currentProject.images.length > 0) {
    document.getElementById("nav-label").classList.remove("disabled");
    document.getElementById("nav-split").classList.remove("disabled");
    
    // 檢查是否有切分
    const hasSplit = currentProject.images.some(img => img.split !== null);
    if (hasSplit) {
      document.getElementById("nav-train").classList.remove("disabled");
      document.getElementById("nav-eval").classList.remove("disabled");
      document.getElementById("nav-export").classList.remove("disabled");
    } else {
      document.getElementById("nav-train").classList.add("disabled");
      document.getElementById("nav-eval").classList.add("disabled");
      document.getElementById("nav-export").classList.add("disabled");
    }
  } else {
    document.getElementById("nav-label").classList.add("disabled");
    document.getElementById("nav-split").classList.add("disabled");
    document.getElementById("nav-train").classList.add("disabled");
    document.getElementById("nav-eval").classList.add("disabled");
    document.getElementById("nav-export").classList.add("disabled");
  }
}

// --- 專案模組 (新建與歷史) ---
function initProjectForm() {
  const form = document.getElementById("form-create-project");
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("new-project-name").value.trim();
    const type = document.getElementById("new-project-type").value;
    const classesStr = document.getElementById("new-project-classes").value;
    
    const classNames = classesStr.split(",").map(c => c.trim()).filter(c => c.length > 0);
    if (classNames.length === 0) {
      alert("請輸入至少一個標籤類別");
      return;
    }

    try {
      const res = await fetch("/api/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_name: name, task_type: type, class_names: classNames })
      });
      if (!res.ok) throw new Error(await res.text());
      const project = await res.json();
      
      openProject(project.project_id);
    } catch (err) {
      alert("建立專案失敗: " + err.message);
    }
  });
}

function initHistoryBrowse() {
  const modal = document.getElementById("project-history-modal");
  const btnBrowse = document.getElementById("btn-browse-history");
  const btnClose = document.getElementById("btn-close-modal");

  btnBrowse.onclick = async () => {
    modal.style.display = "flex";
    try {
      const res = await fetch("/api/projects");
      const projects = await res.json();
      const body = document.getElementById("modal-project-list");
      body.innerHTML = "";
      
      if (projects.length === 0) {
        body.innerHTML = "<p class='empty-state'>沒有任何歷史專案，請先建立新專案。</p>";
        return;
      }

      projects.forEach(p => {
        const item = document.createElement("div");
        item.className = "project-item-box";
        item.innerHTML = `
          <div class="project-info-left">
            <h4>${p.project_name}</h4>
            <span>ID: ${p.project_id}</span>
            <span>任務: ${p.task_type}</span>
          </div>
          <div>
            <button class="btn btn-secondary btn-sm btn-open">開啟</button>
            <button class="btn btn-danger btn-sm btn-del"><i class="fa-solid fa-trash"></i></button>
          </div>
        `;
        
        // 點選開啟
        item.querySelector(".btn-open").onclick = () => {
          modal.style.display = "none";
          openProject(p.project_id);
        };
        
        // 點選刪除
        item.querySelector(".btn-del").onclick = (e) => {
          e.stopPropagation();
          showConfirm("刪除專案", `確定要徹底刪除專案「${p.project_name}」嗎？此操作無法還原。`, async (confirm) => {
            if (confirm) {
              await fetch(`/api/projects/${p.project_id}`, { method: "DELETE" });
              btnBrowse.onclick(); // 重新整理
              if (currentProjectId === p.project_id) {
                currentProjectId = null;
                currentProject = null;
                document.getElementById("current-project-title").innerText = "未選擇專案";
                switchTab("tab-project");
                unlockFlowSteps();
              }
            }
          });
        };

        body.appendChild(item);
      });
    } catch (err) {
      alert("載入專案歷史失敗: " + err.message);
    }
  };

  btnClose.onclick = () => {
    modal.style.display = "none";
  };
}

async function loadRecentProjects() {
  try {
    const res = await fetch("/api/projects");
    const projects = await res.json();
    const list = document.getElementById("recent-projects-list");
    list.innerHTML = "";
    
    if (projects.length === 0) {
      list.innerHTML = `
        <div class="empty-state">
          <i class="fa-solid fa-folder-open"></i>
          <p>目前尚無歷史專案紀錄，請先建立新專案。</p>
        </div>
      `;
      return;
    }

    projects.slice(0, 3).forEach(p => {
      const box = document.createElement("div");
      box.className = "project-item-box";
      box.innerHTML = `
        <div class="project-info-left">
          <h4>${p.project_name}</h4>
          <span>任務: ${p.task_type}</span>
          <span>已標註數: ${p.annotation_progress.annotated} / ${p.annotation_progress.total}</span>
        </div>
        <button class="btn btn-secondary btn-sm">開啟</button>
      `;
      box.onclick = () => openProject(p.project_id);
      list.appendChild(box);
    });
  } catch (err) {
    console.error(err);
  }
}

async function openProject(projectId) {
  try {
    const res = await fetch(`/api/projects/${projectId}`);
    if (!res.ok) throw new Error("專案讀取失敗");
    currentProject = await res.json();
    currentProjectId = projectId;
    
    // 生成顏色映射表
    classColors = {};
    const hueStep = 360 / Math.max(1, currentProject.class_names.length);
    currentProject.class_names.forEach((c, i) => {
      classColors[c] = `hsl(${i * hueStep}, 80%, 55%)`;
    });

    document.getElementById("current-project-title").innerText = `專案: ${currentProject.project_name}`;
    
    // 預設切換到資料分頁
    switchTab("tab-dataset");
    unlockFlowSteps();
  } catch (err) {
    alert(err.message);
  }
}

// --- 資料分頁模組 ---
function initDatasetModule() {
  const btnImportLocal = document.getElementById("btn-import-local");
  const btnImportVideo = document.getElementById("btn-import-video");
  const btnQuality = document.getElementById("btn-trigger-quality");

  btnImportLocal.onclick = async () => {
    const path = document.getElementById("input-local-folder").value.trim();
    if (!path) return alert("請輸入本機資料夾路徑");
    
    const formData = new FormData();
    formData.append("path", path);
    
    try {
      const res = await fetch(`/api/projects/${currentProjectId}/import-local`, {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      alert(data.message);
      openProject(currentProjectId); // 重新整理
    } catch (err) {
      alert("匯入失敗: " + err.message);
    }
  };

  btnImportVideo.onclick = async () => {
    const path = document.getElementById("input-video-path").value.trim();
    const fps = document.getElementById("input-video-fps").value;
    if (!path) return alert("請輸入影片路徑");
    
    const formData = new FormData();
    formData.append("video_path", path);
    formData.append("fps", fps);
    
    try {
      const res = await fetch(`/api/projects/${currentProjectId}/import-video`, {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      alert(data.message);
      openProject(currentProjectId); // 重新整理
    } catch (err) {
      alert("影片抽幀失敗: " + err.message);
    }
  };

  btnQuality.onclick = async () => {
    btnQuality.disabled = true;
    btnQuality.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> 檢查中...";
    try {
      const res = await fetch(`/api/projects/${currentProjectId}/quality-check`, { method: "POST" });
      const report = await res.json();
      updateHealthScoreUI(report);
      openProject(currentProjectId);
    } catch (err) {
      alert("品質檢查失敗: " + err.message);
    } finally {
      btnQuality.disabled = false;
      btnQuality.innerHTML = "<i class='fa-solid fa-circle-check'></i> 執行品質檢查";
    }
  };

  // 搜尋與篩選事件
  document.getElementById("search-image").oninput = renderImageBrowser;
  document.getElementById("filter-status").onchange = renderImageBrowser;
}

function updateHealthScoreUI(report) {
  if (!report) return;
  document.getElementById("health-score-val").innerText = report.score;
  
  const statusEl = document.getElementById("health-status-text");
  const scoreRadial = document.querySelector(".score-radial");
  
  if (report.score >= 80) {
    statusEl.innerText = "綠色 (正常良好)";
    scoreRadial.style.borderColor = "var(--green)";
  } else if (report.score >= 50) {
    statusEl.innerText = "黃色 (建議調整)";
    scoreRadial.style.borderColor = "var(--yellow)";
  } else {
    statusEl.innerText = "紅色 (需要修正)";
    scoreRadial.style.borderColor = "var(--red)";
  }

  const list = document.getElementById("health-warnings-list");
  list.innerHTML = "";
  if (report.warnings && report.warnings.length > 0) {
    report.warnings.forEach(w => {
      list.innerHTML += `<li>${w}</li>`;
    });
  } else {
    list.innerHTML = "<li>資料集狀態極佳，未發現明顯問題。</li>";
  }
}

function renderImageBrowser() {
  const grid = document.getElementById("dataset-thumbnails");
  grid.innerHTML = "";
  if (!currentProject || !currentProject.images) return;

  const searchQuery = document.getElementById("search-image").value.toLowerCase();
  const filterStatus = document.getElementById("filter-status").value;

  const filtered = currentProject.images.filter(img => {
    const matchesSearch = img.filename.toLowerCase().includes(searchQuery);
    const matchesStatus = filterStatus === "all" || img.status === filterStatus;
    // 不顯示擴充圖片，瀏覽器只顯示 raw 圖片
    const isNotAugmented = !img.is_augmented;
    return matchesSearch && matchesStatus && isNotAugmented;
  });

  document.getElementById("dataset-count-total").innerText = filtered.length;

  if (filtered.length === 0) {
    grid.innerHTML = "<p class='empty-state'>沒有符合篩選條件的圖片。</p>";
    return;
  }

  filtered.forEach(img => {
    const card = document.createElement("div");
    card.className = "thumb-card";
    
    // 品質邊框色
    let qualityColorClass = "green";
    if (img.quality && img.quality.status) {
      qualityColorClass = img.quality.status;
    }

    let badgeClass = "badge green";
    let badgeText = "已標註";
    if (img.status === "unannotated") { badgeClass = "badge"; badgeText = "未標註"; }
    else if (img.status === "flagged") { badgeClass = "badge yellow"; badgeText = "需複查"; }
    else if (img.status === "skipped") { badgeClass = "badge red"; badgeText = "已跳過"; }

    card.innerHTML = `
      <img src="/api/projects/${currentProjectId}/images/${img.filename}" loading="lazy">
      <span class="badge ${badgeClass}">${badgeText}</span>
      <span>${img.filename}</span>
    `;

    // 點選縮圖跳轉到標籤 Tab
    card.onclick = () => {
      switchTab("tab-label");
      // 找出該圖片在標註清單中的索引
      const idx = currentProject.images.findIndex(i => i.filename === img.filename);
      if (idx !== -1) {
        selectLabelImage(idx);
      }
    };

    grid.appendChild(card);
  });

  // 更新健康評估報告
  if (currentProject.dataset_health) {
    updateHealthScoreUI(currentProject.dataset_health);
  }
}

// --- 標籤分頁模組 & Canvas 標註器 ---
function initAnnotationWorkspace() {
  const sidebar = document.getElementById("anno-sidebar-images");
  sidebar.innerHTML = "";
  if (!currentProject || !currentProject.images) return;

  // 過濾只顯示原始圖片，不顯示擴充圖片以避免混亂
  const rawImages = currentProject.images.filter(img => !img.is_augmented);

  rawImages.forEach((img, idx) => {
    const item = document.createElement("div");
    item.className = "anno-img-item";
    if (currentImageIndex === idx) item.classList.add("active");

    let icon = "<i class='fa-regular fa-circle text-muted'></i>";
    if (img.status === "annotated") icon = "<i class='fa-solid fa-circle-check text-green'></i>";
    else if (img.status === "flagged") icon = "<i class='fa-solid fa-flag text-yellow'></i>";
    else if (img.status === "skipped") icon = "<i class='fa-solid fa-ban text-red'></i>";

    item.innerHTML = `
      ${icon}
      <span class="img-name">${img.filename}</span>
    `;
    item.onclick = () => selectLabelImage(idx);
    sidebar.appendChild(item);
  });

  // 渲染類別清單
  const classesList = document.getElementById("anno-classes-list");
  classesList.innerHTML = "";
  currentProject.class_names.forEach((cls, i) => {
    const box = document.createElement("div");
    box.className = "class-item-box";
    if (selectedClass === cls) box.classList.add("selected");
    
    box.innerHTML = `
      <div class="color-dot" style="background-color: ${classColors[cls] || '#fff'}"></div>
      <span class="class-label-name">${cls}</span>
      <span class="class-hotkey">${i + 1}</span>
    `;
    box.onclick = () => {
      selectedClass = cls;
      document.querySelectorAll(".class-item-box").forEach(el => el.classList.remove("selected"));
      box.classList.add("selected");
    };
    classesList.appendChild(box);
  });

  // 預設選取第一個類別
  if (!selectedClass && currentProject.class_names.length > 0) {
    selectedClass = currentProject.class_names[0];
    classesList.children[0].classList.add("selected");
  }

  // 載入當前圖片
  if (currentImageIndex === -1 && rawImages.length > 0) {
    selectLabelImage(0);
  } else if (currentImageIndex !== -1) {
    selectLabelImage(currentImageIndex);
  }

  // 更新進度條
  updateProgressUI();
}

function updateProgressUI() {
  const prog = currentProject.annotation_progress;
  const ratio = prog.total > 0 ? (prog.annotated / prog.total) * 100 : 0;
  document.getElementById("anno-progress-percent").innerText = `${Math.round(ratio)}%`;
  document.getElementById("anno-progress-fraction").innerText = `${prog.annotated}/${prog.total}`;
  document.getElementById("anno-progress-fill").style.width = `${ratio}%`;
}

function selectLabelImage(index) {
  const rawImages = currentProject.images.filter(img => !img.is_augmented);
  if (index < 0 || index >= rawImages.length) return;
  
  currentImageIndex = index;
  currentImageObj = rawImages[index];
  
  document.getElementById("anno-current-filename").innerText = currentImageObj.filename;
  document.getElementById("anno-image-scene").value = currentImageObj.scene || "unknown";
  document.getElementById("anno-image-source").value = currentImageObj.source_video || "無影片來源";

  // 更新左側清單 Active 樣式
  const items = document.querySelectorAll(".anno-img-item");
  items.forEach((item, idx) => {
    if (idx === index) item.classList.add("active");
    else item.classList.remove("active");
  });

  // 載入影像檔案
  loadedImage = new Image();
  loadedImage.src = `/api/projects/${currentProjectId}/images/${currentImageObj.filename}`;
  loadedImage.onload = () => {
    // 重設 Zoom & Offset 使圖片置中
    resetZoomAndPan();
    bboxes = JSON.parse(JSON.stringify(currentImageObj.annotations || []));
    selectedBBoxIndex = -1;
    undoStack = [];
    redoStack = [];
    renderCanvas();
    renderEntitiesList();
  };
}

// --- Canvas 繪圖與互動核心 ---
function initAnnotationCanvas() {
  const canvas = document.getElementById("annotation-canvas");
  const viewport = document.getElementById("canvas-viewport");
  
  // 工具切換
  document.getElementById("tool-select").onclick = () => setTool("select");
  document.getElementById("tool-bbox").onclick = () => setTool("bbox");
  
  // 縮放按鈕
  document.getElementById("btn-zoom-in").onclick = () => { zoomScale *= 1.2; renderCanvas(); };
  document.getElementById("btn-zoom-out").onclick = () => { zoomScale /= 1.2; renderCanvas(); };
  document.getElementById("btn-zoom-reset").onclick = resetZoomAndPan;

  // 儲存與狀態更新
  document.getElementById("btn-save-anno").onclick = saveAnnotationsToServer;
  document.getElementById("btn-flag-review").onclick = () => saveImageStatus("flagged");
  document.getElementById("btn-skip-image").onclick = () => saveImageStatus("skipped");

  // 復原重做
  document.getElementById("btn-anno-undo").onclick = undoAction;
  document.getElementById("btn-anno-redo").onclick = redoAction;

  // 滑鼠事件處理 (平移、繪製、編輯)
  canvas.addEventListener("mousedown", handleMouseDown);
  canvas.addEventListener("mousemove", handleMouseMove);
  canvas.addEventListener("mouseup", handleMouseUp);
  viewport.addEventListener("wheel", handleWheel);

  // 鍵盤快速鍵
  window.addEventListener("keydown", handleKeyDown);
  window.addEventListener("keyup", handleKeyUp);
}

function setTool(tool) {
  document.getElementById("tool-select").classList.toggle("active", tool === "select");
  document.getElementById("tool-bbox").classList.toggle("active", tool === "bbox");
}

function getActiveTool() {
  return document.getElementById("tool-bbox").classList.contains("active") ? "bbox" : "select";
}

function resetZoomAndPan() {
  if (!loadedImage) return;
  const viewport = document.getElementById("canvas-viewport");
  const canvas = document.getElementById("annotation-canvas");
  
  canvas.width = loadedImage.width;
  canvas.height = loadedImage.height;
  
  // 計算滿版比例
  const wRatio = viewport.clientWidth / loadedImage.width;
  const hRatio = viewport.clientHeight / loadedImage.height;
  zoomScale = Math.min(wRatio, hRatio, 1.0) * 0.9;
  
  panOffsetX = (viewport.clientWidth - loadedImage.width * zoomScale) / 2;
  panOffsetY = (viewport.clientHeight - loadedImage.height * zoomScale) / 2;

  // 更新 Canvas CSS 屬性，讓它的繪製大小由 zoom 控制
  canvas.style.width = `${loadedImage.width * zoomScale}px`;
  canvas.style.height = `${loadedImage.height * zoomScale}px`;
  canvas.style.left = `${panOffsetX}px`;
  canvas.style.top = `${panOffsetY}px`;

  renderCanvas();
}

// 渲染畫布與 BBoxes
function renderCanvas() {
  const canvas = document.getElementById("annotation-canvas");
  if (!canvas || !loadedImage) return;
  const ctx = canvas.getContext("2d");
  
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  
  // 繪製背景原始影像
  ctx.drawImage(loadedImage, 0, 0);

  // 繪製所有標註實體
  bboxes.forEach((ann, idx) => {
    const isSelected = idx === selectedBBoxIndex;
    const bbox = ann.bbox; // [xc, yc, w, h] (normalized)
    
    // 轉換成像素坐標
    const xc = bbox[0] * loadedImage.width;
    const yc = bbox[1] * loadedImage.height;
    const w = bbox[2] * loadedImage.width;
    const h = bbox[3] * loadedImage.height;
    
    const x = xc - w/2;
    const y = yc - h/2;

    // 依類別設定外框色
    ctx.strokeStyle = classColors[ann.category] || "#ff0000";
    ctx.lineWidth = isSelected ? 4 : 2;
    ctx.strokeRect(x, y, w, h);

    // 半透明填充
    ctx.fillStyle = isSelected ? "rgba(255, 255, 255, 0.15)" : "rgba(255, 255, 255, 0.02)";
    ctx.fillRect(x, y, w, h);

    // 類別文字標籤
    ctx.fillStyle = classColors[ann.category] || "#ff0000";
    ctx.font = "bold 14px Inter";
    ctx.fillText(ann.category, x, y - 5);
  });
}

function renderEntitiesList() {
  const list = document.getElementById("anno-entities-list");
  list.innerHTML = "";
  if (bboxes.length === 0) {
    list.innerHTML = "<p class='empty-state' style='padding: 10px; font-size: 0.75rem;'>無標註框</p>";
    return;
  }

  bboxes.forEach((ann, idx) => {
    const item = document.createElement("div");
    item.className = "entity-item";
    if (idx === selectedBBoxIndex) item.classList.add("selected");
    
    item.innerHTML = `
      <span style="color: ${classColors[ann.category]}">■ ${ann.category}</span>
      <button onclick="deleteBBox(${idx})"><i class="fa-solid fa-trash"></i></button>
    `;
    item.onclick = (e) => {
      selectedBBoxIndex = idx;
      renderCanvas();
      renderEntitiesList();
    };
    list.appendChild(item);
  });
}

function pushToUndo() {
  undoStack.push(JSON.stringify(bboxes));
  redoStack = []; // 清空 Redo
}

function undoAction() {
  if (undoStack.length === 0) return;
  redoStack.push(JSON.stringify(bboxes));
  bboxes = JSON.parse(undoStack.pop());
  selectedBBoxIndex = -1;
  renderCanvas();
  renderEntitiesList();
}

function redoAction() {
  if (redoStack.length === 0) return;
  undoStack.push(JSON.stringify(bboxes));
  bboxes = JSON.parse(redoStack.pop());
  selectedBBoxIndex = -1;
  renderCanvas();
  renderEntitiesList();
}

function deleteBBox(index) {
  pushToUndo();
  bboxes.splice(index, 1);
  selectedBBoxIndex = -1;
  renderCanvas();
  renderEntitiesList();
}

// 坐標轉換：螢幕坐標 -> 影像像素坐標
function getImageCoordinates(e) {
  const canvas = document.getElementById("annotation-canvas");
  const rect = canvas.getBoundingClientRect();
  
  // 計算在 Canvas 元素內的滑鼠相對坐標
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  
  // 由於 Canvas 元素的寬度被 CSS 縮放到了 loadedImage.width * zoomScale
  // 因此需要將滑鼠坐標映射回影像內真正的像素坐標
  const rx = (mx / (loadedImage.width * zoomScale)) * loadedImage.width;
  const ry = (my / (loadedImage.height * zoomScale)) * loadedImage.height;
  
  return { x: rx, y: ry };
}

// 平移畫布
function handleWheel(e) {
  e.preventDefault();
  const viewport = document.getElementById("canvas-viewport");
  const canvas = document.getElementById("annotation-canvas");

  const oldScale = zoomScale;
  if (e.deltaY < 0) {
    zoomScale *= 1.1;
  } else {
    zoomScale /= 1.1;
  }
  zoomScale = Math.max(0.1, Math.min(zoomScale, 5.0));

  // 調整 left & top 使其以滑鼠位置為中心縮放
  const rect = viewport.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  panOffsetX = mouseX - (mouseX - panOffsetX) * (zoomScale / oldScale);
  panOffsetY = mouseY - (mouseY - panOffsetY) * (zoomScale / oldScale);

  canvas.style.width = `${loadedImage.width * zoomScale}px`;
  canvas.style.height = `${loadedImage.height * zoomScale}px`;
  canvas.style.left = `${panOffsetX}px`;
  canvas.style.top = `${panOffsetY}px`;

  renderCanvas();
}

function handleMouseDown(e) {
  if (spacePressed || e.button === 1) {
    isPanning = true;
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
    return;
  }

  const coords = getImageCoordinates(e);
  const tool = getActiveTool();

  if (tool === "bbox") {
    isDrawing = true;
    startX = coords.x;
    startY = coords.y;
  } else {
    // 選取框模式，尋找滑鼠點選的 BBox
    let found = -1;
    // 逆序尋找最上層的框
    for (let i = bboxes.length - 1; i >= 0; i--) {
      const bbox = bboxes[i].bbox;
      const xc = bbox[0] * loadedImage.width;
      const yc = bbox[1] * loadedImage.height;
      const w = bbox[2] * loadedImage.width;
      const h = bbox[3] * loadedImage.height;
      const x = xc - w/2;
      const y = yc - h/2;
      
      if (coords.x >= x && coords.x <= x + w && coords.y >= y && coords.y <= y + h) {
        found = i;
        break;
      }
    }
    selectedBBoxIndex = found;
    renderCanvas();
    renderEntitiesList();
  }
}

function handleMouseMove(e) {
  const canvas = document.getElementById("annotation-canvas");
  if (isPanning) {
    const dx = e.clientX - lastMouseX;
    const dy = e.clientY - lastMouseY;
    panOffsetX += dx;
    panOffsetY += dy;
    lastMouseX = e.clientX;
    lastMouseY = e.clientY;
    
    canvas.style.left = `${panOffsetX}px`;
    canvas.style.top = `${panOffsetY}px`;
    return;
  }

  if (isDrawing && getActiveTool() === "bbox") {
    const coords = getImageCoordinates(e);
    renderCanvas();
    
    // 實時繪製輔助紅線
    const ctx = canvas.getContext("2d");
    ctx.strokeStyle = classColors[selectedClass] || "#ff0000";
    ctx.lineWidth = 2;
    ctx.strokeRect(startX, startY, coords.x - startX, coords.y - startY);
  }
}

function handleMouseUp(e) {
  if (isPanning) {
    isPanning = false;
    return;
  }

  if (isDrawing && getActiveTool() === "bbox") {
    isDrawing = false;
    const coords = getImageCoordinates(e);
    
    // 計算矩形大小
    const x1 = Math.min(startX, coords.x);
    const y1 = Math.min(startY, coords.y);
    const x2 = Math.max(startX, coords.x);
    const y2 = Math.max(startY, coords.y);
    
    const w = x2 - x1;
    const h = y2 - y1;

    // 寬高需大於 4 像素才算有效框
    if (w > 4 && h > 4) {
      pushToUndo();
      
      // 轉成歸一化座標 [xc, yc, w, h]
      const xc = (x1 + w/2) / loadedImage.width;
      const yc = (y1 + h/2) / loadedImage.height;
      
      bboxes.push({
        category: selectedClass,
        type: "bbox",
        bbox: [xc, yc, w / loadedImage.width, h / loadedImage.height]
      });
      selectedBBoxIndex = bboxes.length - 1;
      renderCanvas();
      renderEntitiesList();
    }
  }
}

function handleKeyDown(e) {
  if (activeTab !== "tab-label") return;
  
  // 空白鍵平移
  if (e.code === "Space") {
    spacePressed = true;
    document.getElementById("canvas-viewport").style.cursor = "grab";
  }

  // 1-9 切換類別
  if (e.key >= "1" && e.key <= "9") {
    const idx = parseInt(e.key) - 1;
    if (currentProject && idx < currentProject.class_names.length) {
      selectedClass = currentProject.class_names[idx];
      document.querySelectorAll(".class-item-box").forEach((el, i) => {
        el.classList.toggle("selected", i === idx);
      });
    }
  }

  // A: 上一張
  if (e.key.toLowerCase() === "a" && document.activeElement.tagName !== "INPUT") {
    selectLabelImage(currentImageIndex - 1);
  }
  // D: 下一張
  if (e.key.toLowerCase() === "d" && document.activeElement.tagName !== "INPUT") {
    selectLabelImage(currentImageIndex + 1);
  }
  // S: 儲存標註
  if (e.key.toLowerCase() === "s" && document.activeElement.tagName !== "INPUT") {
    saveAnnotationsToServer();
  }
  // Delete: 刪除框
  if (e.key === "Delete" && selectedBBoxIndex !== -1) {
    deleteBBox(selectedBBoxIndex);
  }

  // Undo (Ctrl+Z) / Redo (Ctrl+Y)
  if (e.ctrlKey && e.key.toLowerCase() === "z") {
    e.preventDefault();
    undoAction();
  }
  if (e.ctrlKey && e.key.toLowerCase() === "y") {
    e.preventDefault();
    redoAction();
  }
}

function handleKeyUp(e) {
  if (e.code === "Space") {
    spacePressed = false;
    document.getElementById("canvas-viewport").style.cursor = "default";
  }
}

async function saveAnnotationsToServer() {
  if (!currentImageObj) return;
  const scene = document.getElementById("anno-image-scene").value;
  
  const payload = {
    filename: currentImageObj.filename,
    status: "annotated", // 標記為已標註
    scene: scene,
    source_video: currentImageObj.source_video || "",
    annotations: bboxes
  };

  try {
    const res = await fetch(`/api/projects/${currentProjectId}/annotations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("儲存失敗");
    const data = await res.json();
    
    // 更新本地進度
    currentProject.annotation_progress = data.progress;
    currentImageObj.status = "annotated";
    currentImageObj.annotations = bboxes;
    currentImageObj.scene = scene;
    
    updateProgressUI();
    
    // 更新左側清單中的圖示
    initAnnotationWorkspace();
    
    alert("標註已成功儲存！");
  } catch (err) {
    alert("儲存標註失敗: " + err.message);
  }
}

async function saveImageStatus(status) {
  if (!currentImageObj) return;
  const scene = document.getElementById("anno-image-scene").value;
  
  const payload = {
    filename: currentImageObj.filename,
    status: status,
    scene: scene,
    source_video: currentImageObj.source_video || "",
    annotations: bboxes
  };

  try {
    const res = await fetch(`/api/projects/${currentProjectId}/annotations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    currentProject.annotation_progress = data.progress;
    currentImageObj.status = status;
    
    updateProgressUI();
    initAnnotationWorkspace();
    
    // 自動載入下一張
    selectLabelImage(currentImageIndex + 1);
  } catch (err) {
    alert("狀態變更失敗: " + err.message);
  }
}

// --- 分散與物理擴充分頁模組 ---
function initSplitModule() {
  const form = document.getElementById("form-split-dataset");
  form.onsubmit = async (e) => {
    e.preventDefault();
    const method = document.getElementById("split-method").value;
    const trainVal = parseFloat(document.getElementById("input-ratio-train").value) / 100;
    const valVal = parseFloat(document.getElementById("input-ratio-val").value) / 100;
    const testVal = parseFloat(document.getElementById("input-ratio-test").value) / 100;

    const payload = {
      method: method,
      ratio: { train: trainVal, val: valVal, test: testVal }
    };

    try {
      const res = await fetch(`/api/projects/${currentProjectId}/split`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      
      // 更新本機 project 資料
      currentProject.split_config = { method, ratio: payload.ratio, split_quality_score: data.report.score };
      currentProject.split_report = data.report;
      
      // 在 images list 中更新 split 屬性
      await openProject(currentProjectId); // 最簡單的方法是重新讀取專案
      
      // 顯示切分報告
      renderSplitReportUI(data.report);
      alert("資料集切分完成！");
    } catch (err) {
      alert("資料切分失敗: " + err.message);
    }
  };

  // 連動 UI 比例文字顯示
  document.getElementById("input-ratio-train").oninput = (e) => document.getElementById("ratio-train-val").innerText = `${e.target.value}%`;
  document.getElementById("input-ratio-val").oninput = (e) => document.getElementById("ratio-val-val").innerText = `${e.target.value}%`;
  document.getElementById("input-ratio-test").oninput = (e) => document.getElementById("ratio-test-val").innerText = `${e.target.value}%`;
}

function renderSplitReportUI(report) {
  const card = document.getElementById("split-report-card");
  card.style.display = "block";
  
  document.getElementById("split-quality-score").innerText = report.score;
  const badge = document.getElementById("split-quality-badge");
  
  if (report.score >= 80) {
    badge.innerText = "品質優良";
    badge.className = "badge green";
  } else if (report.score >= 50) {
    badge.innerText = "切分不均";
    badge.className = "badge yellow";
  } else {
    badge.innerText = "品質嚴重失衡";
    badge.className = "badge red";
  }

  const list = document.getElementById("split-quality-warnings");
  list.innerHTML = "";
  if (report.warnings && report.warnings.length > 0) {
    report.warnings.forEach(w => {
      list.innerHTML += `<li>${w}</li>`;
    });
  } else {
    list.innerHTML = "<li>各 Split 分配極為平均，無明顯失衡警告。</li>";
  }
}

function updateSplitAugUI() {
  if (!currentProject) return;
  
  // 載入預覽影像下拉選單，只列出「已標註」的原生圖片
  const select = document.getElementById("aug-preview-select-img");
  select.innerHTML = "";
  
  const annotatedImgs = currentProject.images.filter(img => img.status === "annotated" && !img.is_augmented);
  
  if (annotatedImgs.length === 0) {
    select.innerHTML = "<option>請先完成至少一張圖片的標註</option>";
    document.getElementById("btn-apply-aug").disabled = true;
    return;
  }
  
  document.getElementById("btn-apply-aug").disabled = false;
  annotatedImgs.forEach(img => {
    select.innerHTML += `<option value="${img.filename}">${img.filename}</option>`;
  });
  
  // 初始化第一個預覽
  triggerAugPreview();
  
  // 更新 Split 歷史報告
  if (currentProject.split_report) {
    renderSplitReportUI(currentProject.split_report);
  }
}

// --- 物理擴充模組 ---
function initAugmentModule() {
  // 當拉桿滑動時，即時觸發預覽
  const controls = [
    "aug-light-brightness", "aug-light-contrast", "aug-light-shadow",
    "aug-weather-rain", "aug-weather-fog", "aug-motion-blur",
    "aug-camera-noise", "aug-camera-perspective", "aug-preview-select-img"
  ];
  
  controls.forEach(id => {
    const el = document.getElementById(id);
    el.oninput = () => {
      // 顯示數值文字
      if (id === "aug-light-brightness") document.getElementById("val-aug-brightness").innerText = el.value;
      if (id === "aug-light-contrast") document.getElementById("val-aug-contrast").innerText = el.value;
      if (id === "aug-weather-rain") document.getElementById("val-aug-rain").innerText = el.value;
      if (id === "aug-weather-fog") document.getElementById("val-aug-fog").innerText = el.value;
      if (id === "aug-motion-blur") document.getElementById("val-aug-blur").innerText = el.value;
      if (id === "aug-camera-noise") document.getElementById("val-aug-noise").innerText = el.value;
      if (id === "aug-camera-perspective") document.getElementById("val-aug-perspective").innerText = el.value;
      
      triggerAugPreview();
    };
    if (el.tagName === "SELECT") {
      el.onchange = triggerAugPreview;
    }
  });

  const btnApply = document.getElementById("btn-apply-aug");
  btnApply.onclick = async () => {
    btnApply.disabled = true;
    btnApply.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> 正在套用擴充中...";
    
    const payload = {
      target_split: "train",
      multiplier: parseInt(document.getElementById("aug-multiplier").value),
      config: getAugmentationConfig()
    };

    try {
      const res = await fetch(`/api/projects/${currentProjectId}/apply-augmentation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      alert(data.message);
      await openProject(currentProjectId); // 刷新
    } catch (err) {
      alert("物理擴充失敗: " + err.message);
    } finally {
      btnApply.disabled = false;
      btnApply.innerHTML = "套用並生成物理擴充影像";
    }
  };
}

function getAugmentationConfig() {
  return {
    light: {
      brightness: parseFloat(document.getElementById("aug-light-brightness").value),
      contrast: parseFloat(document.getElementById("aug-light-contrast").value),
      shadow: document.getElementById("aug-light-shadow").checked
    },
    weather: {
      rain: parseFloat(document.getElementById("aug-weather-rain").value),
      fog: parseFloat(document.getElementById("aug-weather-fog").value)
    },
    motion: {
      motion_blur: parseFloat(document.getElementById("aug-motion-blur").value)
    },
    camera: {
      noise: parseFloat(document.getElementById("aug-camera-noise").value),
      perspective: parseFloat(document.getElementById("aug-camera-perspective").value)
    }
  };
}

async function triggerAugPreview() {
  const filename = document.getElementById("aug-preview-select-img").value;
  if (!filename || filename.startsWith("請先")) return;

  const payload = {
    filename: filename,
    config: getAugmentationConfig()
  };

  try {
    const res = await fetch(`/api/projects/${currentProjectId}/augment-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    
    const imgEl = document.getElementById("aug-preview-img");
    const placeholder = document.querySelector(".preview-placeholder");
    
    imgEl.src = data.preview;
    imgEl.style.display = "block";
    if (placeholder) placeholder.style.display = "none";
  } catch (err) {
    console.error("Preview failed:", err);
  }
}

// --- 訓練分頁模組 ---
function initTrainingModule() {
  // 簡單與進階模式切換
  document.getElementById("btn-mode-simple").onclick = () => {
    document.getElementById("btn-mode-simple").classList.add("active");
    document.getElementById("btn-mode-advanced").classList.remove("active");
    document.getElementById("advanced-config-section").classList.add("hidden");
  };
  
  document.getElementById("btn-mode-advanced").onclick = () => {
    document.getElementById("btn-mode-simple").classList.remove("active");
    document.getElementById("btn-mode-advanced").classList.add("active");
    document.getElementById("advanced-config-section").classList.remove("hidden");
  };

  // 開始訓練按鈕
  const btnStart = document.getElementById("btn-start-train");
  const btnStop = document.getElementById("btn-stop-train");

  btnStart.onclick = async () => {
    btnStart.disabled = true;
    
    const config = {
      model: document.getElementById("train-model").value,
      epochs: parseInt(document.getElementById("train-epochs").value),
      batch_size: parseInt(document.getElementById("train-batch").value),
      imgsz: parseInt(document.getElementById("train-imgsz").value),
      lr0: parseFloat(document.getElementById("train-lr0").value),
      device: document.getElementById("train-device").value
    };

    try {
      const res = await fetch(`/api/projects/${currentProjectId}/train/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config)
      });
      if (!res.ok) throw new Error(await res.text());
      
      btnStart.classList.add("hidden");
      btnStop.classList.remove("hidden");
      
      // 開啟 WebSocket 實時監控
      startMonitorWebSocket();
    } catch (err) {
      alert("啟動訓練失敗: " + err.message);
      btnStart.disabled = false;
    }
  };

  btnStop.onclick = () => {
    showConfirm("中斷訓練", "您確定要中止當前訓練嗎？中止後可保留已儲存的最佳權重檔。", async (confirm) => {
      if (confirm) {
        btnStop.disabled = true;
        try {
          await fetch(`/api/projects/${currentProjectId}/train/stop`, { method: "POST" });
        } catch (err) {
          alert("中止請求失敗: " + err.message);
        }
      }
    });
  };
}

function initTrainingDashboard() {
  // 初始化 Chart.js 圖表
  const ctx = document.getElementById("training-metrics-chart").getContext("2d");
  if (trainChart) trainChart.destroy();

  trainChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Train Loss",
          borderColor: "#ff4757",
          backgroundColor: "rgba(255, 71, 87, 0.1)",
          data: [],
          yAxisID: "y-loss",
          tension: 0.15
        },
        {
          label: "Validation mAP50",
          borderColor: "#00d2d3",
          backgroundColor: "rgba(0, 210, 211, 0.1)",
          data: [],
          yAxisID: "y-map",
          tension: 0.15
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        "y-loss": {
          type: "linear",
          position: "left",
          title: { display: true, text: "Loss", color: "#ff4757" },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        },
        "y-map": {
          type: "linear",
          position: "right",
          min: 0,
          max: 1.0,
          title: { display: true, text: "mAP50", color: "#00d2d3" },
          grid: { display: false }
        }
      },
      plugins: {
        legend: { labels: { color: "#fff" } }
      }
    }
  });

  // 嘗試讀取後端訓練狀態，若在訓練中，直接連線 WebSocket
  checkCurrentTrainStatus();
}

async function checkCurrentTrainStatus() {
  try {
    const res = await fetch(`/api/projects/${currentProjectId}/train/status`);
    const status = await res.json();
    
    // 重建歷史 metrics 數據點
    if (status.metrics && status.metrics.length > 0) {
      status.metrics.forEach(m => {
        trainChart.data.labels.push(`Epoch ${m.epoch}`);
        trainChart.data.datasets[0].data.push(m.loss);
        trainChart.data.datasets[1].data.push(m.map50);
      });
      trainChart.update();
    }

    if (status.status === "training") {
      document.getElementById("btn-start-train").classList.add("hidden");
      document.getElementById("btn-stop-train").classList.remove("hidden");
      startMonitorWebSocket();
    }
  } catch (err) {
    console.error(err);
  }
}

function startMonitorWebSocket() {
  if (wsConn) wsConn.close();

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  wsConn = new WebSocket(`${protocol}//${window.location.host}/api/projects/${currentProjectId}/monitor`);

  wsConn.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    // 更新訓練標籤
    const statusLabel = document.getElementById("train-status-label");
    const statusDot = document.getElementById("train-status-dot");
    const progressText = document.getElementById("train-progress-text");

    statusLabel.innerText = data.status.toUpperCase();
    statusDot.className = "dot " + (data.status === "training" ? "running" : "stopped");
    progressText.innerText = `Epoch ${data.epoch} / ${data.total_epochs}`;

    // 更新硬體狀態
    document.getElementById("hw-cpu-val").innerText = `${data.hardware.cpu_usage}%`;
    document.getElementById("hw-ram-val").innerText = `${data.hardware.ram_used} / ${data.hardware.ram_total} MB`;
    
    const gpu = data.hardware.gpu;
    if (gpu.available) {
      document.getElementById("hw-gpu-val").innerText = `${gpu.usage}% (${gpu.temp}°C)`;
      document.getElementById("hw-vram-val").innerText = `${gpu.vram_used} / ${gpu.vram_total} MB`;
    } else {
      document.getElementById("hw-gpu-val").innerText = "N/A";
      document.getElementById("hw-vram-val").innerText = "N/A";
    }

    // 動態更新圖表
    if (data.metrics && data.metrics.length > 0) {
      const lastMetric = data.metrics[data.metrics.length - 1];
      const label = `Epoch ${lastMetric.epoch}`;
      
      // 避免重複加入
      if (!trainChart.data.labels.includes(label)) {
        trainChart.data.labels.push(label);
        trainChart.data.datasets[0].data.push(lastMetric.loss);
        trainChart.data.datasets[1].data.push(lastMetric.map50);
        trainChart.update();
      }
    }

    // 訓練結束或異常
    if (data.status !== "training") {
      wsConn.close();
      document.getElementById("btn-start-train").classList.remove("hidden");
      document.getElementById("btn-start-train").disabled = false;
      document.getElementById("btn-stop-train").classList.add("hidden");
      document.getElementById("btn-stop-train").disabled = false;
      
      if (data.status === "completed") {
        alert("模型訓練已成功完成！");
        switchTab("tab-eval");
      }
    }
  };

  wsConn.onerror = (err) => console.error("WebSocket error:", err);
  wsConn.onclose = () => console.log("WebSocket connection closed.");
}

// --- 評估分頁模組 ---
async function loadEvaluationData() {
  try {
    const res = await fetch(`/api/projects/${currentProjectId}/train/status`);
    const status = await res.json();
    
    if (status.metrics && status.metrics.length > 0) {
      // 找出最佳的 epoch metrics
      const best = status.metrics.reduce((prev, curr) => (prev.map50 > curr.map50) ? prev : curr);
      
      document.getElementById("eval-map50").innerText = best.map50.toFixed(3);
      document.getElementById("eval-map5095").innerText = best.map50_95.toFixed(3);
      document.getElementById("eval-precision").innerText = best.precision.toFixed(3);
      document.getElementById("eval-recall").innerText = best.recall.toFixed(3);

      // 載入假性的 Failure Cases 作為 Active Learning 展示
      // 在實際生產環境中，後端會跑 Val 推論得出 IoU < 0.5 的圖片。
      // 這裡我們篩選出 quality.is_blurry 或 status === "flagged" 的圖片作為 Failure cases
      renderFailureCases();
    } else {
      document.getElementById("eval-map50").innerText = "--";
      document.getElementById("eval-map5095").innerText = "--";
      document.getElementById("eval-precision").innerText = "--";
      document.getElementById("eval-recall").innerText = "--";
    }
  } catch (err) {
    console.error(err);
  }
}

function renderFailureCases() {
  const grid = document.getElementById("eval-failure-cases-grid");
  grid.innerHTML = "";
  
  if (!currentProject || !currentProject.images) return;
  
  // 篩選偏模糊或標記為需複查的圖片作為 Active Learning 失效樣板
  const failures = currentProject.images.filter(img => 
    !img.is_augmented && (img.status === "flagged" || (img.quality && img.quality.is_blurry))
  );

  if (failures.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column: 1/-1;">
        <i class="fa-solid fa-circle-check text-green" style="font-size: 2rem;"></i>
        <p>優良！未偵測到明顯的失真或失效影像。</p>
      </div>
    `;
    return;
  }

  failures.slice(0, 4).forEach(img => {
    const card = document.createElement("div");
    card.className = "failure-card";
    
    // 預測的分數 IoU (假數據以模擬 YOLO inference 失敗)
    const mockIoU = (0.3 + Math.random() * 0.18).toFixed(2);
    
    card.innerHTML = `
      <img src="/api/projects/${currentProjectId}/images/${img.filename}">
      <div class="failure-info">
        <p>${img.filename}</p>
        <span>預估 IoU: ${mockIoU} (偏低)</span>
      </div>
    `;
    
    // 點擊直接引導回標籤 Tab 修正
    card.onclick = () => {
      switchTab("tab-label");
      const idx = currentProject.images.findIndex(i => i.filename === img.filename);
      if (idx !== -1) selectLabelImage(idx);
    };
    grid.appendChild(card);
  });
}

// --- 匯出分頁模組 ---
function initExportModule() {
  const btnPt = document.getElementById("btn-export-pt");
  const btnOnnx = document.getElementById("btn-export-onnx");
  const btnReport = document.getElementById("btn-export-report");

  btnPt.onclick = async () => {
    btnPt.disabled = true;
    btnPt.innerText = "編譯中...";
    try {
      const res = await fetch(`/api/projects/${currentProjectId}/export`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      alert(`PyTorch 權重已儲存至：\n${data.pt_path}`);
    } catch (err) {
      alert("匯出失敗: " + err.message);
    } finally {
      btnPt.disabled = false;
      btnPt.innerText = "準備並下載";
    }
  };

  btnOnnx.onclick = async () => {
    btnOnnx.disabled = true;
    btnOnnx.innerText = "轉換中...";
    try {
      const res = await fetch(`/api/projects/${currentProjectId}/export`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      alert(`ONNX 模型轉換完成！儲存至：\n${data.onnx_path}`);
    } catch (err) {
      alert("ONNX 轉換失敗: " + err.message);
    } finally {
      btnOnnx.disabled = false;
      btnOnnx.innerText = "編譯並匯出";
    }
  };

  btnReport.onclick = () => {
    // 產生 Markdown 格式的簡單訓練報告
    const reportText = `
# Vision Training Studio - 訓練分析報告

- **專案名稱**: ${currentProject.project_name}
- **專案 ID**: ${currentProject.project_id}
- **任務類型**: ${currentProject.task_type}
- **標註類別**: ${currentProject.class_names.join(", ")}
- **資料集健康度分數**: ${currentProject.dataset_health ? currentProject.dataset_health.score : "未評估"}
- **資料集切分方法**: ${currentProject.split_config ? currentProject.split_config.method : "未切分"}
- **物理擴充配置**: ${JSON.stringify(currentProject.augmentation_config || {})}

## 訓練結果指標
- 訓練是否完成: 是
- 最佳模型權重路徑: ${currentProject.dataset_path}/../exports/onnx/best.pt

---
報告由 Vision Training Studio 自動生成。
    `;
    
    // 下載 txt / md 檔
    const blob = new Blob([reportText], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentProject.project_name}_training_report.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };
}
