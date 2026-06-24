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

  // 頧???鈭辣蝬?
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
      eventBus.emit("toast", `甇?撠?閮餉?? ${type}...`);
      try {
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/convert`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ export_type: type })
        });
        eventBus.emit("toast", `頧?摰?嚗?????${data.converted_count} ??獢);
        eventBus.emit("refresh-project");
      } catch (err) {
        eventBus.emit("toast", `頧?憭望?嚗?{err.message}`);
      } finally {
        btn.disabled = false;
      }
    });
  });

  // ?＊蝷箇撣賊??桃??詨??孵???
  qs("#chk-show-issues-only")?.addEventListener("change", () => {
    eventBus.emit("state-changed");
  });

  // 璅酉瑼?????訾??喳?
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
        eventBus.emit("toast", "隢?頛?遣蝡?獢?");
        return;
      }

      eventBus.emit("toast", "甇???????殷??舀鞈?憭暸?餈湛?...");
      try {
        const files = await collectDroppedFiles(e.dataTransfer);
        await handleAnnotationUpload(files);
      } catch (err) {
        eventBus.emit("toast", `霈???仿??桀仃??${err.message}`);
      }
    }, true);
  }
}

async function handleAnnotationUpload(files) {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "隢?頛?遣蝡?獢?");
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
    eventBus.emit("toast", `?蕪??${ignoredFiles.length} ??璅酉瑼?嚗???/敶梁?嚗甇方????JSON ??TXT 璅酉瑼??喋);
  }

  if (validFiles.length === 0) {
    eventBus.emit("toast", "?⊥??? .json ??.txt 璅酉瑼?");
    return;
  }

  if (validFiles.length > 2000) {
    eventBus.emit("toast", "?格活銝璅酉瑼???憭?2000 ??隢??嫣??喋?);
    return;
  }

  const batchSize = 200;
  const batches = [];
  for (let i = 0; i < validFiles.length; i += batchSize) {
    batches.push(validFiles.slice(i, i + batchSize));
  }

  eventBus.emit("toast", `??撠??${validFiles.length} ??閮餅?獢???${batches.length} ?嫣??喃葉嚗?..`);
  
  let importedJsons = 0;
  let importedTxts = 0;

  try {
    for (let k = 0; k < batches.length; k++) {
      const currentBatch = batches[k];
      eventBus.emit("toast", `甇?銝蝚?${k + 1}/${batches.length} ?寞?閮餅?獢?(${currentBatch.length} ??...`);
      
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
    
    eventBus.emit("toast", `???閮餅?獢?亙????勗??${importedJsons} ??JSON ??${importedTxts} ??TXT 瑼??);
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", `璅酉瑼??臬憭望?嚗?{err.message}`);
  }
}

async function openExternalLabelMe() {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "隢?頛?遣蝡?獢?);
    return;
  }
  const btn = qs("#btn-open-labelme");
  if (btn) btn.disabled = true;
  eventBus.emit("toast", "甇???憭 LabelMe...");
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/open`, { method: "POST" });
    eventBus.emit("toast", data.message || "LabelMe 撌脣???);
  } catch (err) {
    const message = err.message === "Not Found"
      ? "LabelMe ?? API 撠頛嚗??? FastAPI 敺垢敺?閰艾?
      : `LabelMe ??憭望?嚗?{err.message}`;
    eventBus.emit("toast", message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function syncLabelMeLabels(silent = false) {
  const btn = qs("#btn-sync-labelme");
  if (btn) btn.disabled = true;
  if (!silent) eventBus.emit("toast", "甇?????甇?LabelMe JSON 璅酉瑼?..");
  
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
    if (!silent) eventBus.emit("toast", "?郊摰?嚗?);
  } catch (err) {
    eventBus.emit("toast", `?郊憭望?嚗?{err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

export function renderLabelMeManager(status) {
  const datasetPath = status.datasetPath || "";
  const layoutPaths = appState.currentProject?._layout_report?.paths || {};
  const imagesPath = layoutPaths.raw_images?.path || (datasetPath ? `${datasetPath}/raw/images` : "尚未載入專案");
  const jsonPath = layoutPaths.current_labelme?.path || (datasetPath ? `${datasetPath}/raw/annotations/labelme` : "尚未載入專案");
  const outputPath = layoutPaths.current_yolo?.path || (datasetPath ? `${datasetPath}/raw/labels` : "尚未載入專案");
  setText("#labelme-images-path", imagesPath);
  setText("#labelme-json-path", jsonPath);
  setText("#labelme-output-path", outputPath);
  setText("#labelme-classes", status.classNames.length ? status.classNames.join(", ") : "--");
  setText("#labelme-command", datasetPath ? `labelme "${imagesPath}" --output "${jsonPath}"` : "撠頛撠?");

  // 敺?獢身摰葉??閰喟敦??labelme ?郊?脣漲
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
        <td colspan="5" style="text-align:center;">?∟???? Dataset ??臬????/td>
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
          <i class="fa-solid fa-circle-check" style="color: var(--success); margin-right: 6px; font-size: 1.1rem;"></i> ???獢?撌脫迤蝣箸?閮颱蒂??瑼Ｘ??        </td>
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

    // ?芸?憟敺垢?底蝝啗那?瑞???    if (isCorrupted) {
      statusText = "Corrupted JSON";
      issueText = "JSON ?澆???嚗瘜迤蝣箄圾??;
      fixText = "雿輻 LabelMe ??脣?璅酉";
      rowClass = "row-missing"; // ?臭蝙?函??脤?鈭?    } else if (isEmpty) {
      statusText = "Empty JSON";
      issueText = "JSON ?找??隞颱?璅酉?耦";
      fixText = "??LabelMe ?折??唳??訾蒂摮?";
      rowClass = "row-warning";
    } else if (unknownLabels.length > 0) {
      statusText = "Unknown labels";
      issueText = `??芾酉???? ${unknownLabels.join(", ")}`;
      fixText = "??Dataset ?啣?憿? LabelMe 靽格迤璅惜";
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
      <p>甇?頛 ${escapeHtml(filename)} ?汗...</p>
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
        <p>頛?汗憭望?嚗?{escapeHtml(err.message)}</p>
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
