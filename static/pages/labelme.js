import { eventBus } from "../event_bus.js";
import { appState, getProjectStatus, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setText, setHTML, escapeHtml, copyText, collectDroppedFiles, colorForLabel } from "../utils.js";

export function initLabelMe() {
  eventBus.on("language-changed", () => renderLabelMeManager(getProjectStatus(appState.currentProject)));
  qs("#btn-open-labelme")?.addEventListener("click", openExternalLabelMe);
  qs("#btn-refresh-labelme")?.addEventListener("click", async () => {
    await syncLabelMeLabels(true);
  });
  qs("#btn-sync-labelme")?.addEventListener("click", () => {
    syncLabelMeLabels(false);
  });
  qs("#btn-apply-annotation-import")?.addEventListener("click", applyLatestAnnotationImport);
  qs("#btn-copy-images-path")?.addEventListener("click", () => copyText(qs("#labelme-images-path")?.textContent));
  qs("#btn-copy-json-path")?.addEventListener("click", () => copyText(qs("#labelme-json-path")?.textContent));
  qs("#btn-copy-labelme-command")?.addEventListener("click", () => copyText(qs("#labelme-command")?.textContent));

  const converters = {
    "#btn-convert-yolo-det": "yolo_detection",
    "#btn-convert-yolo-seg": "yolo_segmentation",
    "#btn-convert-coco": "coco",
    "#btn-convert-mask": "semantic_mask"
  };

  Object.entries(converters).forEach(([id, type]) => {
    qs(id)?.addEventListener("click", async () => {
      const btn = qs(id);
      if (btn) btn.disabled = true;
      eventBus.emit("toast", t("labelme.toast.converting", { type }));
      try {
        const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/convert`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ export_type: type })
        });
        eventBus.emit("toast", `Conversion complete. Converted ${data.converted_count || 0} files.`);
        eventBus.emit("refresh-project");
      } catch (err) {
        eventBus.emit("toast", `Conversion failed: ${err.message}`);
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  });

  qs("#chk-show-issues-only")?.addEventListener("change", () => {
    eventBus.emit("state-changed");
  });

  const annoDropZone = qs("#annotations-drop-zone");
  const inputAnnoFile = qs("#input-annotations-file");

  if (annoDropZone && inputAnnoFile) {
    inputAnnoFile.style.display = "none";
    if (annoDropZone.dropzone) annoDropZone.dropzone.destroy();

    annoDropZone.addEventListener("click", () => inputAnnoFile.click());
    inputAnnoFile.addEventListener("change", async (event) => {
      const files = [...(event.target.files || [])];
      if (files.length === 0) return;
      await handleAnnotationUpload(files);
      inputAnnoFile.value = "";
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      annoDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        annoDropZone.classList.add("dz-drag-hover");
      }, true);
    });

    ["dragleave", "dragend"].forEach((eventName) => {
      annoDropZone.addEventListener(eventName, (event) => {
        event.preventDefault();
        event.stopPropagation();
        annoDropZone.classList.remove("dz-drag-hover");
      }, true);
    });

    annoDropZone.addEventListener("drop", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      annoDropZone.classList.remove("dz-drag-hover");

      if (!appState.currentProjectId) {
        eventBus.emit("toast", "Please open a project first.");
        return;
      }

      eventBus.emit("toast", "Scanning dropped annotation files...");
      try {
        const files = await collectDroppedFiles(event.dataTransfer);
        await handleAnnotationUpload(files);
      } catch (err) {
        eventBus.emit("toast", `Failed to read dropped files: ${err.message}`);
      }
    }, true);
  }
}

async function handleAnnotationUpload(files) {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "Please open a project first.");
    return;
  }

  const allFiles = [...files];
  const validFiles = allFiles.filter((file) => {
    const name = file.name.toLowerCase();
    return name.endsWith(".json") || name.endsWith(".txt") || name.endsWith(".csv");
  });
  const ignoredFiles = allFiles.length - validFiles.length;

  if (ignoredFiles > 0) {
    eventBus.emit("toast", `Ignored ${ignoredFiles} unsupported files. Only JSON, TXT, and CSV annotation files are accepted.`);
  }

  if (validFiles.length === 0) {
    eventBus.emit("toast", "No .json, .txt, or .csv annotation files found.");
    return;
  }

  if (validFiles.length > 2000) {
    eventBus.emit("toast", "Too many annotation files. Please upload 2000 files or fewer at a time.");
    return;
  }

  eventBus.emit("toast", `Uploading ${validFiles.length} annotation files...`);

  try {
    const formData = new FormData();
    validFiles.forEach((file) => formData.append("files", file, file.name));

    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/import-annotations`, {
      method: "POST",
      body: formData
    });

    appState.latestAnnotationImport = data.report || null;
    eventBus.emit("toast", `Import complete. JSON: ${data.imported_jsons || 0}, TXT: ${data.imported_txts || 0}, CSV: ${data.imported_csv || 0}, converted: ${data.converted || 0}.`);
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", `Annotation import failed: ${err.message}`);
  }
}

async function applyLatestAnnotationImport() {
  const report = appState.latestAnnotationImport || appState.currentProject?.last_annotation_import;
  if (!appState.currentProjectId || !report?.import_id) {
    eventBus.emit("toast", "No annotation import draft is available to apply.");
    return;
  }

  const btn = qs("#btn-apply-annotation-import");
  if (btn) btn.disabled = true;
  try {
    await apiFetch(`/api/projects/${appState.currentProjectId}/annotations/import/${report.import_id}/apply`, { method: "POST" });
    eventBus.emit("toast", "Imported annotation drafts applied to current LabelMe JSON.");
    await syncLabelMeLabels(true);
    eventBus.emit("refresh-project");
  } catch (err) {
    eventBus.emit("toast", `Apply import draft failed: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function openExternalLabelMe() {
  if (!appState.currentProjectId) {
    eventBus.emit("toast", "Please open a project first.");
    return;
  }
  const btn = qs("#btn-open-labelme");
  if (btn) btn.disabled = true;
  eventBus.emit("toast", t("labelme.toast.opening"));
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/labelme/open`, { method: "POST" });
    eventBus.emit("toast", data.message || t("labelme.toast.launched"));
  } catch (err) {
    const message = err.message === "Not Found"
      ? t("labelme.toast.openUnavailable")
      : t("labelme.toast.openFailed", { message: err.message });
    eventBus.emit("toast", message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function syncLabelMeLabels(silent = false) {
  const btn = qs("#btn-sync-labelme");
  if (btn) btn.disabled = true;
  if (!silent) eventBus.emit("toast", t("labelme.toast.syncing"));

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
    if (!silent) eventBus.emit("toast", t("labelme.toast.syncComplete"));
  } catch (err) {
    eventBus.emit("toast", t("labelme.toast.syncFailed", { message: err.message }));
  } finally {
    if (btn) btn.disabled = false;
  }
}

export function renderLabelMeManager(status) {
  const datasetPath = status.datasetPath || "";
  const layoutPaths = appState.currentProject?._layout_report?.paths || {};
  const imagesPath = layoutPaths.raw_images?.path || (datasetPath ? `${datasetPath}/raw/images` : "No project loaded");
  const jsonPath = layoutPaths.current_labelme?.path || (datasetPath ? `${datasetPath}/raw/annotations/labelme` : "No project loaded");
  const outputPath = layoutPaths.current_yolo?.path || (datasetPath ? `${datasetPath}/raw/labels` : "No project loaded");

  setText("#labelme-images-path", imagesPath);
  setText("#labelme-json-path", jsonPath);
  setText("#labelme-output-path", outputPath);
  setText("#labelme-classes", status.classNames.length ? status.classNames.join(", ") : "--");
  setText("#labelme-command", datasetPath ? `labelme "${imagesPath}" --output "${jsonPath}"` : "No project loaded");

  const labelmeProgress = appState.currentProject?.labelme_progress || {};
  const corruptedJsons = labelmeProgress.corrupted_jsons_list || [];
  const emptyJsons = labelmeProgress.empty_jsons_list || [];
  const unknownLabelsDetail = labelmeProgress.unknown_labels_detail || {};

  const metrics = [
    [t("labelme.metric.totalImages"), status.labelme.totalImages],
    [t("labelme.metric.jsonFiles"), status.labelme.jsonCount],
    [t("labelme.metric.missingJson"), status.labelme.missingJson],
    [t("labelme.metric.emptyJson"), labelmeProgress.empty_json || 0],
    [t("labelme.metric.unknownLabels"), labelmeProgress.unknown_labels ? labelmeProgress.unknown_labels.length : 0],
    [t("labelme.metric.invalidJson"), labelmeProgress.invalid_json || 0]
  ];
  setHTML("#labelme-progress-grid", metrics.map(([label, value]) => `
    <div class="metric-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join(""));
  setText("#labelme-completion-text", `${status.labelme.completionRate}%`);
  const bar = qs("#labelme-completion-bar");
  if (bar) bar.style.width = `${status.labelme.completionRate}%`;
  renderAnnotationImportReport();

  const rawImages = (appState.currentProject?.images || []).filter((img) => !img.is_augmented);
  if (rawImages.length === 0) {
    setHTML("#labelme-check-table", `
      <tr><td colspan="5" style="text-align:center;">${escapeHtml(t("labelme.empty.noImages"))}</td></tr>
    `);
    return;
  }

  const isSegmentationTask = String(status.taskType || "").toLowerCase().includes("segmentation");
  const hasSegmentationBbox = (img) => isSegmentationTask && (img.annotations || []).some((ann) => ann.type === "bbox");
  const showIssuesOnly = qs("#chk-show-issues-only")?.checked ?? true;

  const filteredImages = showIssuesOnly
    ? rawImages.filter((img) => {
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
          <i class="fa-solid fa-circle-check" style="color: var(--success); margin-right: 6px; font-size: 1.1rem;"></i>
          ${escapeHtml(t("labelme.empty.allPass"))}
        </td>
      </tr>
    `);
    return;
  }

  const rows = filteredImages.map((img) => {
    const jsonFilename = img.filename.replace(/\.[^/.]+$/, ".json");
    let statusText = "Unannotated";
    let issueText = "Missing JSON";
    let fixText = t("labelme.fix.annotate");
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
      fixText = t("labelme.fix.review");
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
      fixText = t("labelme.fix.redrawPolygon");
      rowClass = "row-warning";
    }

    if (isCorrupted) {
      statusText = "Corrupted JSON";
      issueText = "JSON cannot be parsed";
      fixText = t("labelme.fix.saveAgain");
      rowClass = "row-missing";
    } else if (isEmpty) {
      statusText = "Empty JSON";
      issueText = "JSON has no shapes";
      fixText = t("labelme.fix.addAnnotations");
      rowClass = "row-warning";
    } else if (unknownLabels.length > 0) {
      statusText = "Unknown labels";
      issueText = `Unknown labels: ${unknownLabels.join(", ")}`;
      fixText = t("labelme.fix.updateClasses");
      rowClass = "row-warning";
    }

    return `
      <tr class="${rowClass}" data-preview-img="${escapeHtml(img.filename)}" style="cursor:pointer;">
        <td><code>${escapeHtml(jsonFilename)}</code></td>
        <td>${escapeHtml(img.filename)}</td>
        <td><span class="badge ${needsPolygon || isCorrupted || isEmpty || unknownLabels.length > 0 ? "badge-warning" : badgeClassForStatus(img.status)}">${escapeHtml(statusText)}</span></td>
        <td>${escapeHtml(issueText)}</td>
        <td>${escapeHtml(fixText)}</td>
      </tr>
    `;
  });
  setHTML("#labelme-check-table", rows.join(""));

  qsa("#labelme-check-table tr").forEach((row) => {
    row.addEventListener("click", () => {
      const filename = row.dataset.previewImg;
      if (filename) previewLabelMeImage(filename);
    });
  });
}

function renderAnnotationImportReport() {
  const report = appState.latestAnnotationImport || appState.currentProject?.last_annotation_import;
  const container = qs("#annotation-import-report");
  const applyBtn = qs("#btn-apply-annotation-import");
  if (!container) return;

  if (!report?.import_id) {
    setHTML("#annotation-import-report", `
      <div class="summary-empty compact">
        <p>${escapeHtml(t("labelme.importReportEmpty"))}</p>
      </div>
    `);
    if (applyBtn) applyBtn.disabled = true;
    return;
  }

  const converted = Number(report.converted || 0);
  const failed = Number(report.failed || 0);
  const warnings = report.warnings || [];
  const errors = report.errors || [];
  if (applyBtn) applyBtn.disabled = converted === 0;

  const metrics = [
    [t("labelme.import.metric.txt"), report.yolo_txt || 0],
    [t("labelme.import.metric.csv"), report.csv || 0],
    [t("labelme.import.metric.json"), report.labelme_json || 0],
    [t("labelme.import.metric.converted"), converted],
    [t("labelme.import.metric.failed"), failed]
  ];
  const issueRows = [...errors, ...warnings].slice(0, 6);

  setHTML("#annotation-import-report", `
    <div class="annotation-import-summary">
      ${metrics.map(([label, value]) => `
        <div class="project-file-metric">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(value)}</strong>
        </div>
      `).join("")}
    </div>
    <div class="annotation-import-meta">
      <span>${escapeHtml(t("labelme.importReportId"))}: <code>${escapeHtml(report.import_id)}</code></span>
      <span>${escapeHtml(t("labelme.importReportCreated"))}: ${escapeHtml(report.created_at || "--")}</span>
    </div>
    ${issueRows.length ? `
      <div class="annotation-import-issues">
        ${issueRows.map((item) => `
          <div class="summary-warning-item">
            <strong>${escapeHtml(item.file || "--")}</strong>
            <span>${escapeHtml(item.message || "")}</span>
          </div>
        `).join("")}
      </div>
    ` : `<p class="form-hint ready">${escapeHtml(t("labelme.importReportNoIssues"))}</p>`}
  `);
}

async function previewLabelMeImage(filename) {
  const panel = qs("#labelme-preview-panel");
  if (!panel) return;

  panel.innerHTML = `
    <div class="preview-placeholder">
      <i class="fa-solid fa-spinner fa-spin"></i>
      <p>Loading ${escapeHtml(filename)}...</p>
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
      shapes.forEach((shape) => {
        const pts = shape.points || [];
        if (pts.length < 2) return;

        ctx.strokeStyle = colorForLabel(shape.label);
        ctx.lineWidth = Math.max(3, img.width / 300);
        ctx.fillStyle = "rgba(0, 210, 211, 0.15)";

        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i += 1) {
          ctx.lineTo(pts[i][0], pts[i][1]);
        }

        if (shape.shape_type === "rectangle") {
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
        <p>Preview failed: ${escapeHtml(err.message)}</p>
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
