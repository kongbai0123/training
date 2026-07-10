import { t } from "../state.js";
import { escapeHtml } from "../utils.js";

const CNN_PHASES = [
  {
    number: 1,
    titleKey: "trainingFlow.cnn.phase.dataset",
    className: "dataset",
    stages: [
      ["fa-folder-plus", "trainingFlow.stage.project"],
      ["fa-images", "trainingFlow.cnn.stage.import"],
      ["fa-tags", "trainingFlow.cnn.stage.classes"]
    ],
    noteKey: "trainingFlow.cnn.note.dataset"
  },
  {
    number: 2,
    titleKey: "trainingFlow.cnn.phase.annotation",
    className: "annotation",
    stages: [
      ["fa-pen-nib", "trainingFlow.cnn.stage.annotation"],
      ["fa-wand-sparkles", "trainingFlow.cnn.stage.autoLabel"],
      ["fa-magnifying-glass-chart", "trainingFlow.cnn.stage.quality"]
    ],
    noteKey: "trainingFlow.cnn.note.annotation"
  },
  {
    number: 3,
    titleKey: "trainingFlow.cnn.phase.training",
    className: "training",
    stages: [
      ["fa-code-branch", "trainingFlow.cnn.stage.split"],
      ["fa-wand-magic-sparkles", "trainingFlow.cnn.stage.augmentation"],
      ["fa-microchip", "trainingFlow.cnn.stage.train"]
    ],
    noteKey: "trainingFlow.cnn.note.training"
  },
  {
    number: 4,
    titleKey: "trainingFlow.cnn.phase.delivery",
    className: "delivery",
    stages: [
      ["fa-chart-column", "trainingFlow.cnn.stage.evaluate"],
      ["fa-scale-balanced", "trainingFlow.cnn.stage.compare"],
      ["fa-file-export", "trainingFlow.cnn.stage.export"]
    ],
    noteKey: "trainingFlow.cnn.note.delivery"
  }
];

const RNN_PHASES = [
  {
    number: 1,
    titleKey: "trainingFlow.rnn.phase.schema",
    className: "schema",
    stages: [
      ["fa-folder-plus", "trainingFlow.stage.project"],
      ["fa-file-csv", "trainingFlow.rnn.stage.import"],
      ["fa-table-columns", "trainingFlow.rnn.stage.schema"]
    ],
    noteKey: "trainingFlow.rnn.note.schema"
  },
  {
    number: 2,
    titleKey: "trainingFlow.rnn.phase.sequence",
    className: "sequence",
    stages: [
      ["fa-magnifying-glass-chart", "trainingFlow.rnn.stage.quality"],
      ["fa-crop-simple", "trainingFlow.rnn.stage.window"],
      ["fa-code-branch", "trainingFlow.rnn.stage.split"]
    ],
    noteKey: "trainingFlow.rnn.note.sequence"
  },
  {
    number: 3,
    titleKey: "trainingFlow.rnn.phase.training",
    className: "training",
    stages: [
      ["fa-sliders", "trainingFlow.rnn.stage.configure"],
      ["fa-play", "trainingFlow.rnn.stage.train"]
    ],
    noteKey: "trainingFlow.rnn.note.training"
  },
  {
    number: 4,
    titleKey: "trainingFlow.rnn.phase.delivery",
    className: "delivery",
    stages: [
      ["fa-chart-line", "trainingFlow.rnn.stage.evaluate"],
      ["fa-scale-balanced", "trainingFlow.rnn.stage.compare"],
      ["fa-box-archive", "trainingFlow.rnn.stage.export"]
    ],
    noteKey: "trainingFlow.rnn.note.delivery"
  }
];

const PREVIEW_STAGES = {
  cnn: [
    ["fa-images", "trainingFlow.preview.cnn.data"],
    ["fa-pen-nib", "trainingFlow.preview.cnn.annotation"],
    ["fa-microchip", "trainingFlow.preview.cnn.training"],
    ["fa-chart-column", "trainingFlow.preview.cnn.evaluation"],
    ["fa-file-export", "trainingFlow.preview.cnn.export"]
  ],
  rnn: [
    ["fa-file-csv", "trainingFlow.preview.rnn.data"],
    ["fa-table-columns", "trainingFlow.preview.rnn.schema"],
    ["fa-crop-simple", "trainingFlow.preview.rnn.sequence"],
    ["fa-chart-line", "trainingFlow.preview.rnn.evaluation"],
    ["fa-box-archive", "trainingFlow.preview.rnn.export"]
  ]
};

export function renderTrainingFlowGuide({ mode = null } = {}) {
  if (!mode) return renderFlowPreview();
  const normalizedMode = mode === "rnn" ? "rnn" : "cnn";
  const phases = normalizedMode === "rnn" ? RNN_PHASES : CNN_PHASES;
  return `
    <section class="training-flow-guide" data-flow-mode="${normalizedMode}" data-ui-smoke="training-flow-guide" aria-label="${escapeHtml(t(`trainingFlow.${normalizedMode}.aria`))}">
      <div class="training-flow-heading">
        <div>
          <h2><i class="fa-solid fa-route"></i> ${escapeHtml(t(`trainingFlow.${normalizedMode}.title`))}</h2>
          <p>${escapeHtml(t(`trainingFlow.${normalizedMode}.subtitle`))}</p>
        </div>
        <span class="training-flow-mode-label">${escapeHtml(t(`trainingFlow.${normalizedMode}.mode`))}</span>
      </div>
      <div class="training-flow-phases">
        ${phases.map(renderPhase).join("")}
      </div>
    </section>
  `;
}

function renderFlowPreview() {
  return `
    <section class="training-flow-guide training-flow-guide-preview" data-flow-mode="preview" data-ui-smoke="training-flow-guide" aria-label="${escapeHtml(t("trainingFlow.preview.aria"))}">
      <div class="training-flow-heading">
        <div>
          <h2><i class="fa-solid fa-route"></i> ${escapeHtml(t("trainingFlow.preview.title"))}</h2>
          <p>${escapeHtml(t("trainingFlow.preview.subtitle"))}</p>
        </div>
      </div>
      <div class="training-flow-preview-grid">
        ${renderPreviewLane("cnn", "trainingFlow.preview.cnn.title", "trainingFlow.preview.cnn.note")}
        ${renderPreviewLane("rnn", "trainingFlow.preview.rnn.title", "trainingFlow.preview.rnn.note")}
      </div>
    </section>
  `;
}

function renderPreviewLane(mode, titleKey, noteKey) {
  return `
    <section class="training-flow-preview-lane training-flow-preview-${mode}">
      <header>
        <strong>${escapeHtml(t(titleKey))}</strong>
        <span>${escapeHtml(t(noteKey))}</span>
      </header>
      <div class="training-flow-preview-stages">
        ${PREVIEW_STAGES[mode].map((stage, index) => `
          ${index ? '<i class="fa-solid fa-arrow-right training-flow-arrow" aria-hidden="true"></i>' : ""}
          <span><i class="fa-solid ${stage[0]}"></i>${escapeHtml(t(stage[1]))}</span>
        `).join("")}
      </div>
    </section>
  `;
}

function renderPhase(phase) {
  return `
    <section class="training-flow-phase training-flow-phase-${phase.className}">
      <header>
        <span>${phase.number}</span>
        <h3>${escapeHtml(t(phase.titleKey))}</h3>
      </header>
      <div class="training-flow-stage-row">
        ${phase.stages.map((stage, index) => `
          ${index ? '<i class="fa-solid fa-arrow-right training-flow-arrow" aria-hidden="true"></i>' : ""}
          <article class="training-flow-stage">
            <span class="training-flow-stage-icon"><i class="fa-solid ${stage[0]}"></i></span>
            <strong>${escapeHtml(t(stage[1]))}</strong>
          </article>
        `).join("")}
      </div>
      <p class="training-flow-note">${escapeHtml(t(phase.noteKey))}</p>
    </section>
  `;
}
