import { eventBus } from "../event_bus.js";
import { appState, augmentationPresets } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, escapeHtml } from "../utils.js";

// 控制項 ID 清單
const SLIDERS = [
  "#aug-light-brightness",
  "#aug-light-contrast",
  "#aug-weather-rain",
  "#aug-weather-fog",
  "#aug-motion-blur",
  "#aug-camera-noise",
  "#aug-camera-perspective"
];

const SHADOW = "#aug-light-shadow";
const MULTIPLIER = "#aug-multiplier";
const PREVIEW_SELECT = "#aug-preview-select-img";

export function initAugmentation() {
  // 監聽所有滑桿的拖拽事件，並即時更新數值
  SLIDERS.forEach((selector) => {
    const el = qs(selector);
    if (el) {
      el.addEventListener("input", () => {
        updateSliderLabels();
        invalidatePreview();
      });
      el.addEventListener("change", invalidatePreview);
    }
  });

  // 監聽 Shadow Checkbox 變更
  qs(SHADOW)?.addEventListener("change", invalidatePreview);

  // 監聽 Multiplier 的輸入
  qs(MULTIPLIER)?.addEventListener("input", () => {
    updateEstimatedCount();
    invalidatePreview();
  });

  // 監聽預覽圖片選單變更
  qs(PREVIEW_SELECT)?.addEventListener("change", () => {
    invalidatePreview();
    const filename = qs(PREVIEW_SELECT)?.value;
    if (filename) {
      drawBeforeCanvas(filename);
    }
  });

  // Preset 按鈕事件
  qsa("[data-aug-preset]").forEach((button) => {
    button.addEventListener("click", () => applyAugmentationPreset(button.dataset.augPreset));
  });

  // 預覽按鈕事件
  qs("#btn-preview-aug")?.addEventListener("click", async () => {
    await triggerAugPreview();
  });

  // Apply 按鈕事件
  qs("#btn-apply-aug")?.addEventListener("click", async () => {
    const applyBtn = qs("#btn-apply-aug");
    if (applyBtn.disabled) return;
    
    try {
      applyBtn.disabled = true;
      applyBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processing...`;
      
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/apply-augmentation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_split: "train",
          multiplier: Number(qs(MULTIPLIER).value || 1),
          config: getAugmentationConfig()
        })
      });
      eventBus.emit("toast", data.message || "物理擴充完成");
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `物理擴充失敗：${err.message}`);
    } finally {
      applyBtn.disabled = false;
      applyBtn.innerHTML = `<i class="fa-solid fa-wand-magic-sparkles"></i> Apply Augmentation`;
      invalidatePreview(); // 完成後重新設為需預覽狀態
    }
  });
}

export function renderAugmentationPage(status) {
  const select = qs(PREVIEW_SELECT);
  if (!select) return;
  
  // 篩選出非擴充的且已標註的影像
  const options = (appState.currentProject?.images || [])
    .filter((img) => !img.is_augmented && img.status === "annotated")
    .map((img) => `<option value="${escapeHtml(img.filename)}">${escapeHtml(img.filename)}</option>`);
  
  select.innerHTML = options.length ? options.join("") : `<option value="">沒有可預覽的已標註圖片</option>`;
  
  // 預設更新 Sliders 顯示與預計產出數量
  updateSliderLabels();
  updateEstimatedCount();
  invalidatePreview();

  // 若有預覽影像，則初次繪製 Before Canvas
  const filename = select.value;
  if (filename) {
    drawBeforeCanvas(filename);
  } else {
    resetPreviewUI();
  }
}

// 變更參數時，讓 Preview 狀態無效化
function invalidatePreview() {
  const applyBtn = qs("#btn-apply-aug");
  if (applyBtn) applyBtn.disabled = true;
  
  const alertBox = qs("#aug-info-alert");
  const alertText = qs("#aug-alert-text");
  const alertIcon = qs("#aug-info-alert i");
  
  if (alertBox) {
    alertBox.style.background = "rgba(245, 158, 11, 0.05)";
    alertBox.style.borderColor = "var(--border)";
  }
  if (alertText) {
    alertText.textContent = "請先點選「Generate Preview」預覽效果以評估潛在風險，才可套用擴充。";
    alertText.style.color = "#f59e0b";
  }
  if (alertIcon) {
    alertIcon.className = "fa-solid fa-triangle-exclamation";
    alertIcon.style.color = "#f59e0b";
  }
  
  // 隱藏 After 圖片，顯示 placeholder
  const img = qs("#aug-preview-img");
  const placeholder = qs("#aug-preview-placeholder");
  if (img) img.style.display = "none";
  if (placeholder) {
    placeholder.style.display = "block";
    placeholder.textContent = "點擊「Generate Preview」按鈕進行預覽。";
  }
}

// 當預覽成功時，啟用套用按鈕
function validatePreviewSuccess() {
  const applyBtn = qs("#btn-apply-aug");
  if (applyBtn) applyBtn.disabled = false;
  
  const alertBox = qs("#aug-info-alert");
  const alertText = qs("#aug-alert-text");
  const alertIcon = qs("#aug-info-alert i");
  
  if (alertBox) {
    alertBox.style.background = "rgba(16, 185, 129, 0.05)";
    alertBox.style.borderColor = "rgba(16, 185, 129, 0.2)";
  }
  if (alertText) {
    alertText.textContent = "預覽成功，您可以安全套用擴充參數。";
    alertText.style.color = "#10b981";
  }
  if (alertIcon) {
    alertIcon.className = "fa-solid fa-circle-check";
    alertIcon.style.color = "#10b981";
  }
}

// 更新 slider 旁邊的 label 數值
function updateSliderLabels() {
  SLIDERS.forEach((selector) => {
    const el = qs(selector);
    if (!el) return;
    // 將 #aug-light-brightness 等轉為 #val-brightness
    const valId = selector
      .replace("#aug-light-", "#val-")
      .replace("#aug-weather-", "#val-")
      .replace("#aug-camera-", "#val-")
      .replace("#aug-motion-", "#val-motion-");
    const valSpan = qs(valId);
    if (valSpan) {
      valSpan.textContent = Number(el.value).toFixed(2);
    }
  });
}

// 顯示預計生成數量與提示
function updateEstimatedCount() {
  const trainImages = (appState.currentProject?.images || [])
    .filter((img) => !img.is_augmented && img.status === "annotated" && img.split === "train");
  
  const N = trainImages.length;
  const M = Number(qs(MULTIPLIER)?.value || 1);
  const total = N * M;
  
  const trainCountSpan = qs("#aug-info-train-count");
  const multiplierSpan = qs("#aug-info-multiplier");
  const totalCountSpan = qs("#aug-info-total-count");
  
  if (trainCountSpan) trainCountSpan.textContent = `${N} 張`;
  if (multiplierSpan) multiplierSpan.textContent = `${M}x`;
  if (totalCountSpan) {
    totalCountSpan.textContent = `${total} 張`;
    if (total > 500) {
      totalCountSpan.style.color = "#ef4444";
    } else {
      totalCountSpan.style.color = "var(--primary)";
    }
  }
}

// 重設預覽 UI
function resetPreviewUI() {
  const beforeCanvas = qs("#aug-before-canvas");
  const beforePlaceholder = qs("#aug-before-placeholder");
  const img = qs("#aug-preview-img");
  const placeholder = qs("#aug-preview-placeholder");
  
  if (beforeCanvas) beforeCanvas.style.display = "none";
  if (beforePlaceholder) {
    beforePlaceholder.style.display = "block";
    beforePlaceholder.textContent = "選擇已標註且已 split 的影像。";
  }
  if (img) img.style.display = "none";
  if (placeholder) {
    placeholder.style.display = "block";
    placeholder.textContent = "點擊「Generate Preview」按鈕進行預覽。";
  }
}

// 繪製 Before Canvas (原始影像 + BBox/Polygon Overlay)
function drawBeforeCanvas(filename) {
  const canvas = qs("#aug-before-canvas");
  const placeholder = qs("#aug-before-placeholder");
  if (!canvas || !appState.currentProject) return;

  const imgMetadata = (appState.currentProject.images || []).find((img) => img.filename === filename);
  if (!imgMetadata) {
    resetPreviewUI();
    return;
  }

  if (placeholder) placeholder.style.display = "none";
  canvas.style.display = "block";

  const ctx = canvas.getContext("2d");
  const img = new Image();
  img.onload = () => {
    canvas.width = img.width;
    canvas.height = img.height;
    ctx.drawImage(img, 0, 0);

    const annotations = imgMetadata.annotations || [];
    annotations.forEach((ann) => {
      ctx.strokeStyle = "#10B981"; // 綠色框
      ctx.lineWidth = Math.max(3, Math.round(img.width / 250));
      ctx.fillStyle = "rgba(16, 185, 129, 0.15)"; // 半透明綠

      let pts = [];
      const type = ann.type || (ann.points ? "polygon" : "bbox");

      if (type === "polygon" && ann.points && ann.points.length > 0) {
        if (Array.isArray(ann.points[0])) {
          pts = ann.points;
        } else if (typeof ann.points[0] === "number") {
          for (let i = 0; i < ann.points.length; i += 2) {
            pts.push([ann.points[i], ann.points[i + 1]]);
          }
        }
      }

      if (pts.length >= 3) {
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) {
          ctx.lineTo(pts[i][0], pts[i][1]);
        }
        ctx.closePath();
        ctx.stroke();
        ctx.fill();

        ctx.fillStyle = "#10B981";
        const fontSize = Math.max(12, Math.round(img.width / 45));
        ctx.font = `bold ${fontSize}px sans-serif`;
        const minX = Math.min(...pts.map((p) => p[0]));
        const minY = Math.min(...pts.map((p) => p[1]));
        const textWidth = ctx.measureText(ann.category).width;

        ctx.fillRect(minX, Math.max(0, minY - fontSize - 6), textWidth + 10, fontSize + 6);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(ann.category, minX + 5, Math.max(fontSize, minY - 4));
      } else if (ann.bbox && ann.bbox.length === 4) {
        const [xc, yc, w, h] = ann.bbox;
        const x1 = (xc - w / 2) * img.width;
        const y1 = (yc - h / 2) * img.height;
        const bw = w * img.width;
        const bh = h * img.height;

        ctx.beginPath();
        ctx.rect(x1, y1, bw, bh);
        ctx.stroke();
        ctx.fill();

        ctx.fillStyle = "#10B981";
        const fontSize = Math.max(12, Math.round(img.width / 45));
        ctx.font = `bold ${fontSize}px sans-serif`;
        const textWidth = ctx.measureText(ann.category).width;

        ctx.fillRect(x1, Math.max(0, y1 - fontSize - 6), textWidth + 10, fontSize + 6);
        ctx.fillStyle = "#ffffff";
        ctx.fillText(ann.category, x1 + 5, Math.max(fontSize, y1 - 4));
      }
    });
  };
  img.onerror = () => {
    canvas.style.display = "none";
    if (placeholder) {
      placeholder.style.display = "block";
      placeholder.textContent = "無法載入原始影像。";
    }
  };
  img.src = `/api/projects/${appState.currentProjectId}/images/${filename}`;
}

// 物理擴充 Preset
function applyAugmentationPreset(presetName) {
  const preset = augmentationPresets[presetName];
  if (!preset) return;

  qs("#aug-light-brightness").value = preset.brightness;
  qs("#aug-light-contrast").value = preset.contrast;
  qs("#aug-light-shadow").checked = preset.shadow;
  qs("#aug-weather-rain").value = preset.rain;
  qs("#aug-weather-fog").value = preset.fog;
  qs("#aug-motion-blur").value = preset.motionBlur;
  qs("#aug-camera-noise").value = preset.noise;
  qs("#aug-camera-perspective").value = preset.perspective;

  qsa("[data-aug-preset]").forEach((button) => {
    button.classList.toggle("active", button.dataset.augPreset === presetName);
  });

  updateSliderLabels();
  updateEstimatedCount();

  // Preset 點選後直接生成預覽
  triggerAugPreview();
}

function getAugmentationConfig() {
  return {
    light: {
      brightness: Number(qs("#aug-light-brightness").value),
      contrast: Number(qs("#aug-light-contrast").value),
      shadow: qs("#aug-light-shadow").checked
    },
    weather: {
      rain: Number(qs("#aug-weather-rain").value),
      fog: Number(qs("#aug-weather-fog").value)
    },
    motion: {
      motion_blur: Number(qs("#aug-motion-blur").value)
    },
    camera: {
      noise: Number(qs("#aug-camera-noise").value),
      perspective: Number(qs("#aug-camera-perspective").value)
    }
  };
}

async function triggerAugPreview() {
  const filename = qs(PREVIEW_SELECT)?.value;
  if (!appState.currentProjectId || !filename) return;

  const btn = qs("#btn-preview-aug");
  const img = qs("#aug-preview-img");
  const placeholder = qs("#aug-preview-placeholder");

  try {
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Rendering...`;
    }

    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/augment-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, config: getAugmentationConfig() })
    });

    if (img) {
      img.src = data.preview;
      img.style.display = "block";
    }
    if (placeholder) placeholder.style.display = "none";
    
    validatePreviewSuccess();
  } catch (err) {
    if (img) img.style.display = "none";
    if (placeholder) {
      placeholder.style.display = "block";
      placeholder.textContent = `預覽失敗：${err.message}`;
    }
    const applyBtn = qs("#btn-apply-aug");
    if (applyBtn) applyBtn.disabled = true;
    
    const alertText = qs("#aug-alert-text");
    if (alertText) {
      alertText.textContent = `❌ 預覽失敗：${err.message}`;
      alertText.style.color = "#ef4444";
    }
    const alertIcon = qs("#aug-info-alert i");
    if (alertIcon) {
      alertIcon.className = "fa-solid fa-circle-xmark";
      alertIcon.style.color = "#ef4444";
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i class="fa-solid fa-eye"></i> Generate Preview`;
    }
  }
}
