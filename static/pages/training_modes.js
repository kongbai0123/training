import { eventBus } from "../event_bus.js";
import { appState } from "../state.js";
import { qs, qsa } from "../utils.js";

export const trainingModeState = {
  activeMode: "cnn",
  activeRnnPanel: "overview",
  cnn: {
    backend: "ultralytics_yolo",
    trainingEnabled: true
  },
  rnn: {
    backend: "pytorch_lstm",
    trainingEnabled: false
  }
};

export function initTrainingModeSidebar() {
  qsa("[data-training-mode]").forEach((button) => {
    button.addEventListener("click", () => setTrainingMode(button.dataset.trainingMode));
  });

  qsa("[data-rnn-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      trainingModeState.activeMode = "rnn";
      trainingModeState.activeRnnPanel = button.dataset.rnnNav;
      eventBus.emit("navigate", "training");
      renderTrainingModeSidebar();
      renderTrainingWorkspace();
    });
  });

  qsa("[data-cnn-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      trainingModeState.activeMode = "cnn";
      renderTrainingModeSidebar();
      renderTrainingWorkspace();
    });
  });

  qsa("[data-mode-nav]").forEach((button) => {
    button.addEventListener("click", () => {
      qsa("[data-mode-nav]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      if (button.dataset.modeNav === "overview") {
        trainingModeState.activeRnnPanel = "overview";
        eventBus.emit("navigate", "training");
        renderTrainingModeSidebar();
        renderTrainingWorkspace();
      }
    });
  });

  initRnnPreviewEvents();
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
}

export function setTrainingMode(mode) {
  if (!["cnn", "rnn"].includes(mode) || trainingModeState.activeMode === mode) return;
  trainingModeState.activeMode = mode;
  eventBus.emit("navigate", "training");
  renderTrainingModeSidebar();
  renderTrainingWorkspace();
}

export function renderTrainingModeSidebar() {
  qsa("[data-training-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.trainingMode === trainingModeState.activeMode);
  });

  qs("#cnn-mode-nav")?.classList.toggle("hidden", trainingModeState.activeMode !== "cnn");
  qs("#rnn-mode-nav")?.classList.toggle("hidden", trainingModeState.activeMode !== "rnn");

  qsa("[data-rnn-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.rnnNav === trainingModeState.activeRnnPanel);
  });

  qsa("[data-cnn-nav]").forEach((button) => {
    button.classList.toggle(
      "active",
      trainingModeState.activeMode === "cnn" && button.dataset.cnnNav === appState.currentPage
    );
  });

  qsa("[data-mode-nav]").forEach((button) => {
    button.classList.toggle(
      "active",
      button.dataset.modeNav === "overview"
        ? appState.currentPage === "training"
        : button.dataset.modeNav === appState.currentPage
    );
  });
}

export function renderTrainingWorkspace() {
  const isCnn = trainingModeState.activeMode === "cnn";
  qs("#cnn-workspace")?.classList.toggle("hidden", !isCnn);
  qs("#cnn-workspace")?.classList.toggle("active", isCnn);
  qs("#rnn-workspace")?.classList.toggle("hidden", isCnn);
  qs("#rnn-workspace")?.classList.toggle("active", !isCnn);

  qsa("[data-rnn-panel]").forEach((panel) => {
    const isActive = panel.dataset.rnnPanel === trainingModeState.activeRnnPanel;
    panel.classList.toggle("active", isActive);
  });
}

export function initRnnPreviewEvents() {
  const disabledMessage = "RNN training is disabled in this phase. Readiness validation will be introduced later.";
  qsa(".rnn-disabled-action-hitbox").forEach((hitbox) => hitbox.addEventListener("click", (event) => {
    event.preventDefault();
    eventBus.emit("toast", disabledMessage);
  }));
}
