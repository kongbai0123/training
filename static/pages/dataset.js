import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml, collectDroppedFiles } from "../utils.js";

export function initDataset() {
  // 類別管理事件綁定
  qs("#btn-dataset-add-class")?.addEventListener("click", () => {
    const input = qs("#input-dataset-new-class");
    const name = input?.value.trim();
    if (!name) return;
    if (!appState.currentProjectClasses) {
      appState.currentProjectClasses = [];
    }
    if (appState.currentProjectClasses.includes(name)) {
      eventBus.emit("toast", "此類別已存在！");
      return;
    }
    appState.currentProjectClasses.push(name);
    if (input) input.value = "";
    renderDatasetClassesEditList();
  });

  qs("#input-dataset-new-class")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      qs("#btn-dataset-add-class")?.click();
    }
  });

  qs("#dataset-classes-list-box")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove-dataset-class]");
    if (!btn) return;
    const name = btn.dataset.removeDatasetClass;
    appState.currentProjectClasses = (appState.currentProjectClasses || []).filter(c => c !== name);
    renderDatasetClassesEditList();
  });

  qs("#btn-save-dataset-classes")?.addEventListener("click", async () => {
    if (!appState.currentProjectId) {
      eventBus.emit("toast", "請先選擇專案！");
      return;
    }
    const btn = qs("#btn-save-dataset-classes");
    if (btn) btn.disabled = true;
    try {
      await apiFetch(`/api/projects/${appState.currentProjectId}/classes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ class_names: appState.currentProjectClasses || [] })
      });
      eventBus.emit("toast", "類別更新成功！");
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `類別更新失敗：${err.message}`);
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  qs("#btn-import-local")?.addEventListener("click", async () => {
    const path = qs("#input-local-folder").value.trim();
    if (!path) return eventBus.emit("toast", "請輸入圖片資料夾路徑");
    const formData = new FormData();
    formData.append("path", path);
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-local`, {
        method: "POST",
        body: formData
      });
      eventBus.emit("toast", data.message || "圖片匯入完成");
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `匯入圖片失敗：${err.message}`);
    }
  });

  qs("#btn-import-video")?.addEventListener("click", async () => {
    const videoPath = qs("#input-video-path").value.trim();
    const fps = qs("#input-video-fps").value || "1";
    if (!videoPath) return eventBus.emit("toast", "請輸入影片路徑");
    const formData = new FormData();
    formData.append("video_path", videoPath);
    formData.append("fps", fps);
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-video`, {
        method: "POST",
        body: formData
      });
      eventBus.emit("toast", data.message || "影片抽幀完成");
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `影片抽幀失敗：${err.message}`);
    }
  });

  // 影片拖曳上傳區 (純 JS Drag & Drop)
  const videoDropZone = qs("#video-drop-zone");
  const inputVideoFile = qs("#input-video-file");
  
  if (videoDropZone && inputVideoFile) {
    if (videoDropZone.dropzone) {
      try {
        videoDropZone.dropzone.destroy();
      } catch (e) {
        console.warn("Dropzone destroy failed:", e);
      }
    }
    inputVideoFile.style.display = "none";
    inputVideoFile.multiple = true;
    inputVideoFile.accept = "video/*";

    videoDropZone.addEventListener("click", () => inputVideoFile.click());
    
    inputVideoFile.addEventListener("change", async (event) => {
      await uploadVideoFiles([...(event.target.files || [])]);
      inputVideoFile.value = "";
    });
    
    ["dragenter", "dragover"].forEach((eventName) => {
      videoDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        videoDropZone.classList.add("dz-drag-hover");
      }, true);
    });

    ["dragleave", "drop"].forEach((eventName) => {
      videoDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        videoDropZone.classList.remove("dz-drag-hover");
      }, true);
    });

    videoDropZone.addEventListener("drop", async (event) => {
      const files = await collectDroppedFiles(event.dataTransfer);
      await uploadVideoFiles(files);
    }, true);
  }

  async function uploadVideoFiles(files) {
    if (!appState.currentProjectId) {
      eventBus.emit("toast", "請先載入或建立專案！");
      return;
    }
    const allFiles = [...files];
    const videoFiles = allFiles.filter(f => /\.(mp4|avi|mkv|mov|wmv|flv|webm)$/i.test(f.name));
    const otherFiles = allFiles.filter(f => !/\.(mp4|avi|mkv|mov|wmv|flv|webm)$/i.test(f.name));

    if (otherFiles.length > 0) {
      eventBus.emit("toast", `過濾掉 ${otherFiles.length} 個非影片檔案。影片區只接受影片匯入。`);
    }

    if (videoFiles.length === 0) {
      eventBus.emit("toast", "未找到支援的影片檔案。");
      return;
    }

    if (videoFiles.length > 5) {
      eventBus.emit("toast", "單次最多上傳 5 部影片，以防抽幀時間過長。");
      return;
    }

    const fpsVal = qs("#input-video-fps")?.value || "1";

    let progressPanel = qs("#video-dropzone-progress-panel");
    if (!progressPanel) {
      progressPanel = document.createElement("div");
      progressPanel.id = "video-dropzone-progress-panel";
      progressPanel.className = "ingest-progress-container";
      videoDropZone.parentNode.insertBefore(progressPanel, videoDropZone.nextSibling);
    }

    const updateVideoProgress = (statusText, percent, detailsText) => {
      progressPanel.innerHTML = `
        <div class="ingest-progress-header">
          <span class="ingest-progress-status">${escapeHtml(statusText)}</span>
          <span class="ingest-progress-percent">${percent}%</span>
        </div>
        <div class="ingest-progress-bar-bg">
          <div class="ingest-progress-bar-fill" style="width: ${percent}%"></div>
        </div>
        <div class="ingest-progress-details">${escapeHtml(detailsText)}</div>
      `;
    };

    try {
      for (let idx = 0; idx < videoFiles.length; idx++) {
        const file = videoFiles[idx];
        const percent = Math.round((idx / videoFiles.length) * 100);
        updateVideoProgress(
          "Processing video...",
          percent,
          `Uploading & extracting ${file.name} (${idx + 1}/${videoFiles.length})...`
        );

        const formData = new FormData();
        formData.append("file", file);
        formData.append("fps", fpsVal);

        try {
          const data = await apiFetch(`/api/projects/${appState.currentProjectId}/upload-video`, {
            method: "POST",
            body: formData
          });
          eventBus.emit("toast", `${file.name} 抽幀完成！`);
        } catch (err) {
          eventBus.emit("toast", `${file.name} 抽幀失敗：${err.message}`);
        }
      }
      updateVideoProgress("Completed!", 100, `成功處理所有影片抽幀！`);
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `影片處理出錯：${err.message}`);
    } finally {
      setTimeout(() => {
        qs("#video-dropzone-progress-panel")?.remove();
      }, 5000);
    }
  }

  qs("#btn-trigger-quality")?.addEventListener("click", async () => {
    try {
      const report = await apiFetch(`/api/projects/${appState.currentProjectId}/quality-check`, { method: "POST" });
      eventBus.emit("toast", `品質檢查完成，Health Score: ${report.score}`);
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `品質檢查失敗：${err.message}`);
    }
  });

  // ZIP / 資料夾拖曳上傳
  const zipDropZone = qs("#zip-drop-zone");
  const inputZipFile = qs("#input-zip-file");

  if (zipDropZone && inputZipFile) {
    if (zipDropZone.dropzone) {
      try {
        zipDropZone.dropzone.destroy();
      } catch (e) {
        console.warn("Dropzone destroy failed:", e);
      }
    }
    inputZipFile.style.display = "none";
    inputZipFile.multiple = true;
    inputZipFile.setAttribute("webkitdirectory", "");
    inputZipFile.setAttribute("directory", "");

    zipDropZone.addEventListener("click", () => inputZipFile.click());

    inputZipFile.addEventListener("change", async (event) => {
      await uploadDatasetFiles([...(event.target.files || [])]);
      inputZipFile.value = "";
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      zipDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        zipDropZone.classList.add("dz-drag-hover");
      }, true);
    });

    ["dragleave", "drop"].forEach((eventName) => {
      zipDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        zipDropZone.classList.remove("dz-drag-hover");
      }, true);
    });

    zipDropZone.addEventListener("drop", async (event) => {
      const files = await collectDroppedFiles(event.dataTransfer);
      await uploadDatasetFiles(files);
    }, true);
  }

  async function uploadDatasetFiles(files) {
    if (!appState.currentProjectId) {
      eventBus.emit("toast", "Please load a project first.");
      return;
    }

    const allFiles = [...files];
    if (allFiles.length === 0) {
      eventBus.emit("toast", "No files to upload.");
      return;
    }

    let progressPanel = qs("#zip-dropzone-progress-panel");
    if (!progressPanel) {
      progressPanel = document.createElement("div");
      progressPanel.id = "zip-dropzone-progress-panel";
      progressPanel.className = "ingest-progress-container";
      zipDropZone.parentNode.insertBefore(progressPanel, zipDropZone.nextSibling);
    }

    const updateIngestProgress = (statusText, percent, detailsText) => {
      progressPanel.innerHTML = `
        <div class="ingest-progress-header">
          <span class="ingest-progress-status">${escapeHtml(statusText)}</span>
          <span class="ingest-progress-percent">${percent}%</span>
        </div>
        <div class="ingest-progress-bar-bg">
          <div class="ingest-progress-bar-fill" style="width: ${percent}%"></div>
        </div>
        <div class="ingest-progress-details">${escapeHtml(detailsText)}</div>
      `;
    };

    updateIngestProgress("Filtering files...", 0, "Analyzing drop data...");

    // 進行分流過濾
    const zipFiles = allFiles.filter(file => file.name.toLowerCase().endsWith(".zip"));
    const imageFiles = allFiles.filter(file => /\.(jpg|jpeg|png|bmp)$/i.test(file.name));
    
    // 檢查是否有應分流的影片或標註檔
    const videoFiles = allFiles.filter(file => /\.(mp4|avi|mkv|mov|wmv|flv|webm)$/i.test(file.name));
    const annoFiles = allFiles.filter(file => /\.(json|txt)$/i.test(file.name));

    // 發出警告
    let warningMsg = "";
    if (videoFiles.length > 0 && annoFiles.length > 0) {
      warningMsg = `過濾掉 ${videoFiles.length} 個影片與 ${annoFiles.length} 個標註檔。請改至「影片抽幀」與「LabelMe標註」區匯入。`;
    } else if (videoFiles.length > 0) {
      warningMsg = `過濾掉 ${videoFiles.length} 個影片檔案。請改至「影片抽幀」區匯入。`;
    } else if (annoFiles.length > 0) {
      warningMsg = `過濾掉 ${annoFiles.length} 個標註檔案。請改至「LabelMe標註」區匯入。`;
    }

    if (warningMsg) {
      eventBus.emit("toast", warningMsg);
    }

    if (zipFiles.length === 0 && imageFiles.length === 0) {
      eventBus.emit("toast", "未找到支援的圖片或 ZIP 檔案。");
      progressPanel?.remove();
      return;
    }

    // 限制 500 張圖片
    if (imageFiles.length > 500) {
      eventBus.emit("toast", "單次上傳圖片限制最多 500 張，請分批上傳或使用 ZIP 壓縮檔匯入。");
      progressPanel?.remove();
      return;
    }

    let importedImages = 0;
    let duplicateSameHash = 0;
    let renamedCount = 0;
    let skippedCount = 0;

    try {
      // 處理 ZIP
      for (let idx = 0; idx < zipFiles.length; idx++) {
        const zipFile = zipFiles[idx];
        const percent = Math.round((idx / zipFiles.length) * 100);
        updateIngestProgress("Importing ZIP...", percent, `Processing ZIP: ${zipFile.name}...`);
        
        const formData = new FormData();
        formData.append("file", zipFile, zipFile.name);
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-zip`, {
          method: "POST",
          body: formData
        });
        importedImages += data.imported_images || 0;
      }

      // 處理分批圖片上傳 (每批 50 張)
      if (imageFiles.length > 0) {
        const batchSize = 50;
        const totalBatches = Math.ceil(imageFiles.length / batchSize);
        for (let i = 0; i < imageFiles.length; i += batchSize) {
          const batchIndex = Math.floor(i / batchSize) + 1;
          const currentBatch = imageFiles.slice(i, i + batchSize);
          const percent = Math.round((i / imageFiles.length) * 100);
          
          updateIngestProgress(
            "Uploading images...",
            percent,
            `Uploading batch ${batchIndex}/${totalBatches} (${currentBatch.length} files)...`
          );

          const formData = new FormData();
          currentBatch.forEach(file => {
            formData.append("files", file, file.name);
          });

          const data = await apiFetch(`/api/projects/${appState.currentProjectId}/upload-images`, {
            method: "POST",
            body: formData
          });

          importedImages += data.uploaded_count || 0;
          duplicateSameHash += data.duplicate_same_hash || 0;
          renamedCount += data.renamed_same_name_diff_hash || 0;
          skippedCount += data.skipped_count || 0;
        }
      }

      // Sync 標註
      updateIngestProgress("Syncing LabelMe...", 95, "Syncing annotations with project profile...");
      try {
        await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/sync`, { method: "POST" });
      } catch (e) {
        console.warn("Auto sync failed:", e);
      }

      updateIngestProgress(
        "Completed!",
        100,
        `成功匯入 ${importedImages} 張圖片。跳過重複內容 ${duplicateSameHash}，重新命名 ${renamedCount}。`
      );
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `Dataset import failed: ${err.message}`);
      updateIngestProgress("Failed", 100, `Error: ${err.message}`);
    } finally {
      setTimeout(() => {
        qs("#zip-dropzone-progress-panel")?.remove();
      }, 5000);
    }
  }

  qs("#btn-copy-zip-path")?.addEventListener("click", () => {
    const text = qs("#dataset-zip-storage-path")?.textContent;
    if (text && text !== "尚未載入專案" && text !== "尚未載入") {
      navigator.clipboard.writeText(text).then(() => eventBus.emit("toast", "路徑已複製"));
    }
  });

  qs("#search-image")?.addEventListener("input", () => {
    appState.datasetVisibleLimit = 80;
    renderDatasetPage(getProjectStatus(appState.currentProject));
  });
  qs("#filter-status")?.addEventListener("change", () => {
    appState.datasetVisibleLimit = 80;
    renderDatasetPage(getProjectStatus(appState.currentProject));
  });
  qs("#dataset-thumbnails")?.addEventListener("click", (event) => {
    if (!event.target.closest("#btn-load-more-images")) return;
    appState.datasetVisibleLimit += 80;
    renderDatasetPage(getProjectStatus(appState.currentProject));
  });
}

export function renderDatasetPage(status) {
  const project = appState.currentProject;
  const rawImages = (project?.images || []).filter((img) => !img.is_augmented);
  const zipPath = status.datasetPath ? `${status.datasetPath}/packages/zip` : "尚未載入專案";
  setText("#dataset-zip-storage-path", zipPath);

  // 渲染資料集類別編輯清單
  const classesListBox = qs("#dataset-classes-list-box");
  if (classesListBox) {
    if (!appState.currentProjectClasses && project) {
      appState.currentProjectClasses = [...(project.class_names || [])];
    }
    renderDatasetClassesEditList();
  }

  const query = qs("#search-image")?.value?.toLowerCase() || "";
  const filter = qs("#filter-status")?.value || "all";
  const filtered = rawImages.filter((img) => {
    const matchesQuery = img.filename.toLowerCase().includes(query);
    const matchesFilter = filter === "all" || img.status === filter;
    return matchesQuery && matchesFilter;
  });
  setText("#dataset-count-total", filtered.length);
  setText("#health-score-val", project?.dataset_health?.score ?? "--");
  if (!status.hasProject) {
    setHTML("#dataset-thumbnails", `<div class="empty-state">請先載入專案。</div>`);
    return;
  }
  if (filtered.length === 0) {
    setHTML("#dataset-thumbnails", `<div class="empty-state">目前沒有符合條件的圖片。</div>`);
    return;
  }
  const visibleImages = filtered.slice(0, appState.datasetVisibleLimit);
  const hiddenCount = Math.max(0, filtered.length - visibleImages.length);
  const cards = visibleImages.map((img) => `
    <article class="thumb-card">
      <div class="thumb-image-frame">
        <img
          src="/api/projects/${encodeURIComponent(appState.currentProjectId)}/thumbnails/${encodeURIComponent(img.filename)}"
          loading="lazy"
          decoding="async"
          fetchpriority="low"
          alt="${escapeHtml(img.filename)}"
        >
      </div>
      <footer>
        <strong title="${escapeHtml(img.filename)}">${escapeHtml(img.filename)}</strong>
        <span class="badge ${badgeClassForStatus(img.status)}">${escapeHtml(img.status || "unknown")}</span>
      </footer>
    </article>
  `);
  if (hiddenCount > 0) {
    cards.push(`
      <button type="button" class="load-more-card" id="btn-load-more-images">
        <strong>Load more images</strong>
        <span>${visibleImages.length} / ${filtered.length} shown</span>
      </button>
    `);
  }
  setHTML("#dataset-thumbnails", cards.join(""));
}

function renderDatasetClassesEditList() {
  const box = qs("#dataset-classes-list-box");
  if (!box) return;
  const classes = appState.currentProjectClasses || [];
  if (classes.length === 0) {
    box.innerHTML = '<span class="empty-class-list">目前無類別。請新增類別。</span>';
    return;
  }
  box.innerHTML = classes.map(cls => `
    <span class="class-chip">
      ${escapeHtml(cls)}
      <button type="button" data-remove-dataset-class="${escapeHtml(cls)}" style="border:none;background:none;cursor:pointer;color:var(--text-muted);">&times;</button>
    </span>
  `).join("");
}

function badgeClassForStatus(status) {
  if (status === "annotated") return "badge-success";
  if (status === "flagged") return "badge-warning";
  if (status === "skipped") return "badge-danger";
  return "badge-muted";
}
