import { eventBus } from "../event_bus.js";
import { appState, augmentationPresets, fixedAugmentationValues } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setHTML, escapeHtml } from "../utils.js";

export function initAugmentation() {
  const controls = [
    "#aug-light-brightness",
    "#aug-light-contrast",
    "#aug-light-shadow",
    "#aug-weather-rain",
    "#aug-weather-fog",
    "#aug-motion-blur",
    "#aug-camera-noise",
    "#aug-camera-perspective",
    "#aug-preview-select-img"
  ];
  controls.forEach((selector) => {
    qs(selector)?.addEventListener("input", triggerAugPreview);
    qs(selector)?.addEventListener("change", triggerAugPreview);
  });

  qsa("[data-aug-preset]").forEach((button) => {
    button.addEventListener("click", () => applyAugmentationPreset(button.dataset.augPreset));
  });

  qs("#btn-apply-aug")?.addEventListener("click", async () => {
    try {
      const data = await apiFetch(`/api/projects/${appState.currentProjectId}/apply-augmentation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_split: "train",
          multiplier: Number(qs("#aug-multiplier").value || 1),
          config: getAugmentationConfig()
        })
      });
      eventBus.emit("toast", data.message || "物理擴充完成");
      eventBus.emit("refresh-project");
    } catch (err) {
      eventBus.emit("toast", `物理擴充失敗：${err.message}`);
    }
  });
}

export function renderAugmentationPage(status) {
  const select = qs("#aug-preview-select-img");
  if (!select) return;
  const options = (appState.currentProject?.images || [])
    .filter((img) => !img.is_augmented && img.status === "annotated")
    .map((img) => `<option value="${escapeHtml(img.filename)}">${escapeHtml(img.filename)}</option>`);
  select.innerHTML = options.length ? options.join("") : `<option value="">沒有可預覽的已標註圖片</option>`;
}

function applyAugmentationPreset(presetName) {
  const preset = augmentationPresets[presetName];
  if (!preset) return;
  qs("#aug-light-brightness").checked = Math.abs(preset.brightness) > 0;
  qs("#aug-light-contrast").checked = Math.abs(preset.contrast) > 0;
  qs("#aug-light-shadow").checked = preset.shadow;
  qs("#aug-weather-rain").checked = Math.abs(preset.rain) > 0;
  qs("#aug-weather-fog").checked = Math.abs(preset.fog) > 0;
  qs("#aug-motion-blur").checked = Math.abs(preset.motionBlur) > 0;
  qs("#aug-camera-noise").checked = Math.abs(preset.noise) > 0;
  qs("#aug-camera-perspective").checked = Math.abs(preset.perspective) > 0;

  qsa("[data-aug-preset]").forEach((button) => {
    button.classList.toggle("active", button.dataset.augPreset === presetName);
  });
  triggerAugPreview();
}

function getAugmentationConfig() {
  return {
    light: {
      brightness: qs("#aug-light-brightness").checked ? fixedAugmentationValues.brightness : 0,
      contrast: qs("#aug-light-contrast").checked ? fixedAugmentationValues.contrast : 0,
      shadow: qs("#aug-light-shadow").checked
    },
    weather: {
      rain: qs("#aug-weather-rain").checked ? fixedAugmentationValues.rain : 0,
      fog: qs("#aug-weather-fog").checked ? fixedAugmentationValues.fog : 0
    },
    motion: {
      motion_blur: qs("#aug-motion-blur").checked ? fixedAugmentationValues.motionBlur : 0
    },
    camera: {
      noise: qs("#aug-camera-noise").checked ? fixedAugmentationValues.noise : 0,
      perspective: qs("#aug-camera-perspective").checked ? fixedAugmentationValues.perspective : 0
    }
  };
}

async function triggerAugPreview() {
  const filename = qs("#aug-preview-select-img")?.value;
  if (!appState.currentProjectId || !filename) return;
  try {
    const data = await apiFetch(`/api/projects/${appState.currentProjectId}/augment-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, config: getAugmentationConfig() })
    });
    const img = qs("#aug-preview-img");
    const placeholder = qs("#aug-preview-placeholder");
    if (img) {
      img.src = data.preview;
      img.style.display = "block";
    }
    if (placeholder) placeholder.style.display = "none";
  } catch (err) {
    const img = qs("#aug-preview-img");
    const placeholder = qs("#aug-preview-placeholder");
    if (img) img.style.display = "none";
    if (placeholder) {
      placeholder.style.display = "block";
      placeholder.textContent = `預覽失敗：${err.message}`;
    }
  }
}
