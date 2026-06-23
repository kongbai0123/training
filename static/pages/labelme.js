import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml, copyText, collectDroppedFiles, colorForLabel } from "../utils.js";

export function initLabelMe() {
  qs("#btn-open-labelme")?.addEventListener("click", openExternalLabelMe);
  qs("#btn-refresh-labelme")?.addEventListener("click", async () => {
    await syncLabelMeLabels(true);
  });
  qs("#btn-sync-labelme")?.addEventListener("click", () => {
    syncLabelMeLabels(false);
  });
  qs("#btn-copy-images-path")?.addEventListener("click", () => copyText(qs("#labelme-images-path")?.textContent));
  qs("#btn-copy-json-path")?.addEventListener("click", () => copyText(qs("#labelme-json-path")?.textContent));
  qs("#btn-copy-labelme-command")?.addEventListener("click", () => copyText(qs("#labelme-command")?.textContent));

  // 轉換按鈕事件綁定
  const converters = {
    "#btn-convert-yolo-det": "yolo_detection",
    "#btn-convert-yolo-seg": "yolo_segmentation",
    "#btn-convert-coco": "coco",
    "#btn-convert-mask": "semantic_mask"
  };

  Object.entries(converters).forEach(([id, type]) => {
    qs(id)?.addEventListener("click", async () => {
      const btn = qs(id);
      btn.disabled = true;
      eventBus.emit("toast", `正在將標註轉換為 ${type}...`);
      try {
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/convert`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ export_type: type })
        });
        eventBus.emit("toast", `轉換完成！成功處理 ${data.converted_count} 個檔案。`);
        eventBus.emit("refresh-project");
      } catch (err) {
        eventBus.emit("toast", `轉換失敗：${err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });

  // 僅顯示異常項目的核取方塊監聽
  qs("#chk-show-issues-only")?.addEventListener("change", () => {
    eventBus.emit("state-changed");
  });

  // 標註檔案拖曳與點選上傳區
  const annoDropZone = qs("#annotations-drop-zone");
  const inputAnnoFile = qs("#input-annotations-file");

  if (annoDropZone && inputAnnoFile) {
    inputAnnoFile.style.display = "none";
    if (annoDropZone.dropzone) {
      annoDropZone.dropzone.destroy();
    }

    annoDropZone.addEventListener("click", () => {
      inputAnnoFile.click();
    });

    inputAnnoFile.addEventListener("change", async (event) => {
      const files = [...(event.target.files || [])];
      if (files.length === 0) return;
      await handleAnnotationUpload(files);
      inputAnnoFile.value = "";
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      annoDropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        annoDropZone.classList.add("dz-drag-hover");
      }, true);
    });

    ["dragleave", "dragend"].forEach((eventName) => {
      annoDropZone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        annoDropZone.classList.remove("dz-drag-hover");
      }, true);
    });

    annoDropZone.addEventListener("drop", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      annoDropZone.classList.remove("dz-drag-hover");

      if (!appState.currentProjectId) {
        eventBus.emit("toast", "請先載入或建立專案！");
        return;
      }

      eventBus.emit("toast", "正在掃描拖入的項目（支援資料夾遞迴）...");
      try {
        const files = await collectDroppedFiles(e.dataTransfer);
        await handleAnnotationUpload(files);
      } catch (err) {
        eventBus.emit("toast", `讀取拖入項目失敗：${err.message}`);
      }
    }, true);
  }
}

async function handleAnnotationUpload(files) {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "請先載入或建立專案！");
    return;
  }

  const allFiles = [...files];
  const validFiles = allFiles.filter(file => {
    const name = file.name.toLowerCase();
    return name.endsWith(".json") || name.endsWith(".txt");
  });

  const ignoredFiles = allFiles.filter(file => {
    const name = file.name.toLowerCase();
    return !name.endsWith(".json") && !name.endsWith(".txt");
  });

  if (ignoredFiles.length > 0) {
    eventBus.emit("toast", `過濾掉 ${ignoredFiles.length} 個非標註檔案（如圖片/影片）。在此處僅支援 JSON 或 TXT 標註檔上傳。`);
  }

  if (validFiles.length === 0) {
    eventBus.emit("toast", "無有效的 .json 或 .txt 標註檔！");
    return;
  }

  if (validFiles.length > 2000) {
    eventBus.emit("toast", "單次上傳標註檔案限制最多 2000 個，請分批上傳。");
    return;
  }

  const batchSize = 200;
  const batches = [];
  for (let i = 0; i < validFiles.length; i += batchSize) {
    batches.push(validFiles.slice(i, i + batchSize));
  }

  eventBus.emit("toast", `開始導入共 ${validFiles.length} 個標註檔案（分 ${batches.length} 批上傳中）...`);
  
  let importedJsons = 0;
  let importedTxts = 0;

  try {
    for (let k = 0; k < batches.length; k++) {
      const currentBatch = batches[k];
      eventBus.emit("toast", `正在上傳第 ${k + 1}/${batches.length} 批標註檔案 (${currentBatch.length} 個)...`);
      
      const formData = new FormData();
      currentBatch.forEach(file => {
        formData.append("files", file, file.name);
      });

      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-annotations`, {
        method: "POST",
        body: formData
      });
      
      importedJsons += data.imported_jsons || 0;
      importedTxts += data.imported_txts || 0;
    }
    
    eventBus.emit("toast", `所有標註檔案匯入完成！共匯入 ${importedJsons} 個 JSON 與 ${importedTxts} 個 TXT 檔案。`);
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", `標註檔案匯入失敗：${err.message}`);
  }
}

async function openExternalLabelMe() {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "請先載入或建立專案。");
    return;
  }
  const btn = qs("#btn-open-labelme");
  if (btn) btn.disabled = true;
  eventBus.emit("toast", "正在開啟外部 LabelMe...");
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/open`, { method: "POST" });
    eventBus.emit("toast", data.message || "LabelMe 已啟動。");
  } catch (err) {
    const message = err.message === "Not Found"
      ? "LabelMe 啟動 API 尚未載入，請重啟 FastAPI 後端後再試。"
      : `LabelMe 啟動失敗：${err.message}`;
    eventBus.emit("toast", message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function syncLabelMeLabels(silent = false) {
  const btn = qs("#btn-sync-labelme");
  if (btn) btn.disabled = true;
  if (!silent) eventBus.emit("toast", "正在掃描與同步 LabelMe JSON 標註檔...");
  
  try {
    const report = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/sync`, { method: "POST" });
    
    appState.labelme.jsonCount = report.annotated;
    appState.labelme.missingJson = report.missing_json;
    appState.labelme.invalidJson = report.corrupted_json;
    appState.labelme.totalImages = report.total_images;
    appState.labelme.synced = true;
    appState.labelme.completionRate = report.total_images > 0 ? Math.round((report.annotated / report.total_images) * 100) : 0;
    appState.labelme.unknownClasses = report.unknown_classes;
    
    eventBus.emit("refresh-project");
    if (!silent) eventBus.emit("toast", "同步完成！");
  } catch (err) {
    eventBus.emit("toast", `同步失敗：${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

export function renderLabelMeManager(status) {
  const datasetPath = status.datasetPath || "";
  const imagesPath = datasetPath ? `${datasetPath}/raw/images` : "尚未載入專案";
  const jsonPath = datasetPath ? `${datasetPath}/raw/annotations/labelme` : "尚未載入專案";
  const outputPath = datasetPath ? `${datasetPath}/raw/labels` : "尚未載入專案";
  setText("#labelme-images-path", imagesPath);
  setText("#labelme-json-path", jsonPath);
  setText("#labelme-output-path", outputPath);
  setText("#labelme-classes", status.classNames.length ? status.classNames.join(", ") : "--");
  setText("#labelme-command", datasetPath ? `labelme "${imagesPath}" --output "${jsonPath}"` : "尚未載入專案");

  // 從專案設定中提取詳細的 labelme 同步進度
  const labelmeProgress = appState.currentProject?.labelme_progress || {};
  const corruptedJsons = labelmeProgress.corrupted_jsons_list || [];
  const emptyJsons = labelmeProgress.empty_jsons_list || [];
  const unknownLabelsDetail = labelmeProgress.unknown_labels_detail || {};

  const metrics = [
    ["Total images", status.labelme.totalImages],
    ["LabelMe JSON files", status.labelme.jsonCount],
    ["Missing JSON", status.labelme.missingJson],
    ["Empty JSON", labelmeProgress.empty_json || 0],
    ["Unknown labels", labelmeProgress.unknown_labels ? labelmeProgress.unknown_labels.length : 0],
    ["Invalid JSON", labelmeProgress.invalid_json || 0]
  ];
  setHTML("#labelme-progress-grid", metrics.map(([label, value]) => `
    <div class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join(""));
  setText("#labelme-completion-text", `${status.labelme.completionRate}%`);
  const bar = qs("#labelme-completion-bar");
  if (bar) bar.style.width = `${status.labelme.completionRate}%`;
  const rawImages = (appState.currentProject?.images || []).filter((img) => !img.is_augmented);
  if (rawImages.length === 0) {
    setHTML("#labelme-check-table", `
      <tr>
        <td colspan="5" style="text-align:center;">無資料。請先到 Dataset 頁面匯入圖片。</td>
      </tr>
    `);
    return;
  }

  const isSegmentationTask = String(status.taskType || "").toLowerCase().includes("segmentation");
  const hasSegmentationBbox = (img) => isSegmentationTask && (img.annotations || []).some((ann) => ann.type === "bbox");
  const showIssuesOnly = qs("#chk-show-issues-only")?.checked ?? true;
  
  const filteredImages = showIssuesOnly 
    ? rawImages.filter(img => {
        const jsonFilename = img.filename.replace(/\.[^/.]+$/, ".json");
        const isCorrupted = corruptedJsons.includes(jsonFilename);
        const isEmpty = emptyJsons.includes(jsonFilename);
        const hasUnknown = !!unknownLabelsDetail[jsonFilename];
        const needsPolygon = hasSegmentationBbox(img);
        return img.status !== "annotated" || needsPolygon || isCorrupted || isEmpty || hasUnknown;
      })
    : rawImages;

  if (filteredImages.length === 0) {
    setHTML("#labelme-check-table", `
      <tr>
        <td colspan="5" style="text-align:center; padding: 24px; color: var(--text-muted);">
          <i class="fa-solid fa-circle-check" style="color: var(--success); margin-right: 6px; font-size: 1.1rem;"></i> 所有檔案皆已正確標註並通過檢查。
        </td>
      </tr>
    `);
    return;
  }

  const rows = filteredImages.map(img => {
    const jsonFilename = img.filename.replace(/\.[^/.]+$/, ".json");
    
    let statusText = "Unannotated";
    let issueText = "Missing JSON";
    let fixText = "Use LabelMe to annotate";
    let rowClass = "row-missing";
    
    const isCorrupted = corruptedJsons.includes(jsonFilename);
    const isEmpty = emptyJsons.includes(jsonFilename);
    const unknownLabels = unknownLabelsDetail[jsonFilename] || [];
    const needsPolygon = hasSegmentationBbox(img);

    if (img.status === "annotated") {
      statusText = "Annotated";
      issueText = "None";
      fixText = "None";
      rowClass = "row-success";
    } else if (img.status === "flagged") {
      statusText = "Flagged";
      issueText = "Flagged for review";
      fixText = "Review annotations in LabelMe";
      rowClass = "row-warning";
    } else if (img.status === "skipped") {
      statusText = "Skipped";
      issueText = "Skipped";
      fixText = "None";
      rowClass = "row-muted";
    }

    if (needsPolygon) {
      statusText = "Needs polygon";
      issueText = "Segmentation project contains rectangle / bbox shapes";
      fixText = "Open LabelMe and redraw these labels with polygon";
      rowClass = "row-warning";
    }

    // 優先套用後端的詳細診斷結果
    if (isCorrupted) {
      statusText = "Corrupted JSON";
      issueText = "JSON 格式損壞，無法正確解析";
      fixText = "使用 LabelMe 重新儲存標註";
      rowClass = "row-missing"; // 可使用紅色高亮
    } else if (isEmpty) {
      statusText = "Empty JSON";
      issueText = "JSON 內不包含任何標註圖形";
      fixText = "在 LabelMe 內重新框選並存檔";
      rowClass = "row-warning";
    } else if (unknownLabels.length > 0) {
      statusText = "Unknown labels";
      issueText = `包含未註冊類別: ${unknownLabels.join(", ")}`;
      fixText = "至 Dataset 新增類別或到 LabelMe 修正標籤";
      rowClass = "row-warning";
    }
    
    return `
      <tr class="${rowClass}" data-preview-img="${escapeHtml(img.filename)}" style="cursor:pointer;">
        <td><code>${escapeHtml(jsonFilename)}</code></td>
        <td>${escapeHtml(img.filename)}</td>
        <td><span class="badge ${needsPolygon || isCorrupted || isEmpty || unknownLabels.length > 0 ? "badge-warning" : badgeClassForStatus(img.status)}">${statusText}</span></td>
        <td>${issueText}</td>
        <td>${fixText}</td>
      </tr>
    `;
  });
  setHTML("#labelme-check-table", rows.join(""));
  
  qsa("#labelme-check-table tr").forEach(row => {
    row.addEventListener("click", () => {
      const filename = row.dataset.previewImg;
      if (filename) previewLabelMeImage(filename);
    });
  });
}

async function previewLabelMeImage(filename) {
  const panel = qs("#labelme-preview-panel");
  if (!panel) return;
  
  panel.innerHTML = `
    <div class="preview-placeholder">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <p>正在載入 ${escapeHtml(filename)} 預覽...</p>
    </div>
  `;
  
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/preview/${filename}`);
    
    panel.innerHTML = `
      <div style="position:relative; width:100%; height:100%; display:flex; align-items:center; justify-content:center;">
        <canvas id="lbl-preview-canvas" style="max-width:100%; max-height:100%; object-fit:contain;"></canvas>
      </div>
    `;
    
    const canvas = qs("#lbl-preview-canvas");
    const ctx = canvas.getContext("2d");
    
    const img = new Image();
    img.src = `/api/projects/${appState.currentProjectId}/images/${filename}`;
    
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
      
      const shapes = data.shapes || [];
      shapes.forEach(shape => {
        const pts = shape.points || [];
        if (pts.length < 2) return;
        
        ctx.strokeStyle = colorForLabel(shape.label);
        ctx.lineWidth = Math.max(3, img.width / 300);
        ctx.fillStyle = "rgba(0, 210, 211, 0.15)";
        
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i][0], pts[i][1]);
        }
        
        if (shape.shape_type === "rectangle") {
          ctx.closePath();
          const w = pts[1][0] - pts[0][0];
          const h = pts[1][1] - pts[0][1];
          ctx.strokeRect(pts[0][0], pts[0][1], w, h);
          ctx.fillRect(pts[0][0], pts[0][1], w, h);
        } else {
          ctx.closePath();
          ctx.stroke();
          ctx.fill();
        }
        
        ctx.fillStyle = ctx.strokeStyle;
        ctx.font = `bold ${Math.max(16, img.width / 40)}px Inter`;
        ctx.fillText(shape.label, pts[0][0], pts[0][1] - 8);
      });
    };
  } catch (err) {
    panel.innerHTML = `
      <div class="preview-placeholder text-red">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <p>載入預覽失敗：${escapeHtml(err.message)}</p>
      </div>
    `;
  }
}

function badgeClassForStatus(status) {
  if (status === "annotated") return "badge-success";
  if (status === "flagged") return "badge-warning";
  if (status === "skipped") return "badge-danger";
  return "badge-muted";
}
