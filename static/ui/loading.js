import { escapeHtml } from "../utils.js";

const DEFAULT_SIZE = 132;
const DEFAULT_RADIUS = 50;

function clampPercent(percent) {
  const value = Number(percent);
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function getProgressColor(percent) {
  if (percent >= 100) return "var(--success)";
  if (percent >= 80) return "#14b8a6";
  if (percent >= 40) return "var(--info)";
  return "var(--primary)";
}

function renderCircularProgressMarkup(rootEl, caption) {
  const size = Number(rootEl.dataset.size || DEFAULT_SIZE);
  const radius = Number(rootEl.dataset.radius || DEFAULT_RADIUS);
  const center = size / 2;
  const safeCaption = escapeHtml(caption || rootEl.dataset.caption || "Progress");

  rootEl.innerHTML = `
    <svg class="progress-ring" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
      <circle class="progress-ring__bg" cx="${center}" cy="${center}" r="${radius}"></circle>
      <circle class="progress-ring__value" cx="${center}" cy="${center}" r="${radius}"></circle>
    </svg>
    <div class="progress-ring__label">
      <strong class="progress-ring__value-text">0.0%</strong>
      <span class="progress-ring__caption">${safeCaption}</span>
    </div>
  `;
}

export function createCircularProgress(rootEl, initialPercent = 0, options = {}) {
  if (!rootEl) {
    return {
      set() {},
      animateTo() {},
      setCaption() {}
    };
  }

  if (!rootEl.querySelector(".progress-ring__value")) {
    renderCircularProgressMarkup(rootEl, options.caption);
  }

  const circle = rootEl.querySelector(".progress-ring__value");
  const text = rootEl.querySelector(".progress-ring__value-text");
  const caption = rootEl.querySelector(".progress-ring__caption");
  const radius = Number(rootEl.dataset.radius || DEFAULT_RADIUS);
  const circumference = 2 * Math.PI * radius;
  let currentPercent = 0;

  circle.style.strokeDasharray = `${circumference}`;

  function set(percent) {
    const safePercent = clampPercent(percent);
    currentPercent = safePercent;
    circle.style.strokeDashoffset = `${circumference * (1 - safePercent / 100)}`;
    circle.style.stroke = options.color || getProgressColor(safePercent);
    if (text) text.textContent = `${safePercent.toFixed(1)}%`;
  }

  function animateTo(percent, duration = 900) {
    const targetPercent = clampPercent(percent);
    const startPercent = currentPercent;
    const startedAt = performance.now();

    function step(timestamp) {
      const ratio = Math.min((timestamp - startedAt) / Math.max(1, duration), 1);
      const eased = 1 - Math.pow(1 - ratio, 3);
      set(startPercent + (targetPercent - startPercent) * eased);
      if (ratio < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
  }

  function setCaption(value) {
    if (caption) caption.textContent = value || "";
  }

  set(initialPercent);
  return { set, animateTo, setCaption };
}

