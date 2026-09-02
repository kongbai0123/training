import { eventBus } from "../event_bus.js";
import { appState, t } from "../state.js";
import { apiFetch, apiFetchBlob, apiUpload } from "../api.js";
import { followServerTask } from "../core/task_progress.js";
import { escapeHtml, qs } from "../utils.js";
import { trainingModeState } from "./training_mode_state.js";

const ACTIVE_TRAINING_STATUSES = new Set(["training", "stopping"]);
const TERMINAL_TRAINING_STATUSES = new Set(["completed", "failed", "stopped"]);
const PANELS = new Set(["overview", "data", "training", "inference", "registry", "export"]);

const tabularState = {
  initialized: false,
  root: null,
  projectId: "",
  panel: "overview",
  loading: false,
  workspace: null,
  status: null,
  models: [],
  versions: [],
  exports: [],
  runMetrics: null,
  runMetricsId: "",
  configDraft: null,
  trainingDraft: null,
  rowDraft: "",
  selectedModelId: "",
  selectedExportRunId: "",
  rowResult: null,
  batchResult: null,
  exportResult: null,
  error: "",
  pollingTimer: null,
  polling: false,
  lastTerminalRunId: "",
};

export function initTabularWorkspace() {
  if (tabularState.initialized) return;
  tabularState.initialized = true;
  bindWorkspaceRoot();

  eventBus.on("language-changed", () => renderTabularWorkspace());
  eventBus.on("refresh-project", () => {
    if (!isTabularProject(appState.currentProject)) return;
    void loadTabularWorkspace({ force: true, preserveDraft: true });
  });
  eventBus.on("set-tabular-panel", (panel) => setTabularPanel(panel));
  eventBus.on("tabular-panel-changed", (panel) => setTabularPanel(panel));
  eventBus.on("project-deleted", () => resetTabularState());
}

export function renderTabularWorkspace() {
  bindWorkspaceRoot();
  const root = tabularState.root;
  if (!root) return;

  const project = appState.currentProject;
  const projectId = String(appState.currentProjectId || "");
  if (!projectId || !project) {
    stopStatusPolling();
    root.innerHTML = renderEmptyState(
      text("tabular.empty.projectTitle", "請先選擇表格專案", "Select a Tabular project"),
      text("tabular.empty.projectBody", "建立或開啟 Tabular 專案後，即可匯入 CSV 並建立完整模型。", "Create or open a Tabular project to import CSV data and produce a model."),
    );
    return;
  }
  if (!isTabularProject(project)) {
    stopStatusPolling();
    root.innerHTML = renderEmptyState(
      text("tabular.empty.scopeTitle", "目前專案不是表格模型", "This is not a Tabular project"),
      text("tabular.empty.scopeBody", "Tabular 工作區只會讀取獨立的表格專案，不會改動 CNN 或 RNN 專案。", "The Tabular workspace only reads independent Tabular projects and never changes CNN or RNN projects."),
    );
    return;
  }

  if (tabularState.projectId !== projectId) {
    resetTabularState({ keepPanel: true });
    tabularState.projectId = projectId;
  }
  if (!tabularState.workspace && !tabularState.loading) {
    void loadTabularWorkspace();
  }

  root.innerHTML = renderWorkspaceShell(project);
  syncPanelState();
  updatePollingForStatus();
}

function bindWorkspaceRoot() {
  const root = qs("#tabular-workspace-root")
    || qs("#tabular-workspace")
    || qs("#page-tabular .tabular-workspace-root");
  if (!root || tabularState.root === root) return;
  tabularState.root = root;
  root.addEventListener("click", handleWorkspaceClick);
  root.addEventListener("submit", handleWorkspaceSubmit);
  root.addEventListener("input", captureWorkspaceDraft);
  root.addEventListener("change", captureWorkspaceDraft);
}

function resetTabularState({ keepPanel = false } = {}) {
  stopStatusPolling();
  const panel = keepPanel ? tabularState.panel : "overview";
  Object.assign(tabularState, {
    projectId: "",
    panel,
    loading: false,
    workspace: null,
    status: null,
    models: [],
    versions: [],
    exports: [],
    runMetrics: null,
    runMetricsId: "",
    configDraft: null,
    trainingDraft: null,
    rowDraft: "",
    selectedModelId: "",
    selectedExportRunId: "",
    rowResult: null,
    batchResult: null,
    exportResult: null,
    error: "",
    polling: false,
    pollingTimer: null,
    lastTerminalRunId: "",
  });
}

async function loadTabularWorkspace({ force = false, preserveDraft = false } = {}) {
  const projectId = String(appState.currentProjectId || "");
  if (!projectId || !isTabularProject(appState.currentProject)) return;
  if (tabularState.loading && !force) return;

  tabularState.loading = true;
  tabularState.error = "";
  renderTabularWorkspace();
  const responses = await Promise.allSettled([
    apiFetch(`/api/projects/${projectId}/tabular/workspace`, { dedupe: false }),
    apiFetch(`/api/projects/${projectId}/train/status`, { dedupe: false }),
    apiFetch(`/api/projects/${projectId}/models?scope=all`, { dedupe: false }),
    apiFetch(`/api/projects/${projectId}/models/versions`, { dedupe: false }),
    apiFetch(`/api/projects/${projectId}/exports?limit=12`, { dedupe: false }),
  ]);

  if (projectId !== String(appState.currentProjectId || "")) return;
  const [workspaceResult, statusResult, modelsResult, versionsResult, exportsResult] = responses;
  if (workspaceResult.status === "fulfilled") {
    tabularState.workspace = workspaceResult.value;
    if (!preserveDraft || !tabularState.configDraft) {
      tabularState.configDraft = makeConfigDraft(workspaceResult.value?.config || {});
    }
  } else {
    tabularState.error = workspaceResult.reason?.message || text("tabular.error.workspace", "無法載入表格工作區。", "Unable to load the Tabular workspace.");
  }
  if (statusResult.status === "fulfilled") tabularState.status = statusResult.value;
  if (statusResult.status === "fulfilled") appState.trainingStatus = statusResult.value;
  if (modelsResult.status === "fulfilled") tabularState.models = normalizeModels(modelsResult.value);
  if (versionsResult.status === "fulfilled") tabularState.versions = normalizeVersions(versionsResult.value);
  if (exportsResult.status === "fulfilled") tabularState.exports = normalizeExports(exportsResult.value);
  ensureSelections();
  ensureDrafts();
  tabularState.loading = false;
  renderTabularWorkspace();
  await loadLatestRunMetrics();
}

function ensureDrafts() {
  if (!tabularState.configDraft) tabularState.configDraft = makeConfigDraft(tabularState.workspace?.config || {});
  if (!tabularState.trainingDraft) {
    const config = appState.currentProject?.training_config || {};
    tabularState.trainingDraft = {
      runId: "",
      epochs: numberOr(config.epochs, 100),
      learningRate: numberOr(config.learning_rate ?? config.lr0, 0.05),
      maxDepth: numberOr(config.max_depth, 4),
      subsample: numberOr(config.subsample, 1),
      colsampleBytree: numberOr(config.colsample_bytree, 1),
    };
  }
  if (!tabularState.rowDraft) {
    const columns = tabularState.workspace?.config?.feature_columns || [];
    const example = Object.fromEntries(columns.map((column) => [column, 0]));
    tabularState.rowDraft = JSON.stringify(example, null, 2);
  }
}

function ensureSelections() {
  const modelIds = new Set(tabularState.models.map((item) => item.model_id));
  if (!modelIds.has(tabularState.selectedModelId)) {
    tabularState.selectedModelId = tabularState.models[0]?.model_id || "";
  }
  const runs = completedTabularRuns();
  const runIds = new Set(runs.map((item) => item.run_id));
  if (!runIds.has(tabularState.selectedExportRunId)) {
    tabularState.selectedExportRunId = runs[0]?.run_id || tabularState.models[0]?.run_id || "";
  }
}

function renderWorkspaceShell(project) {
  const workspace = tabularState.workspace || {};
  const inspection = workspace.inspection || {};
  const validation = workspace.validation || {};
  const status = tabularState.status || {};
  const ready = Boolean(workspace.ready);
  const statusName = String(status.status || "idle");
  return `
    <section class="tabular-workspace" aria-busy="${tabularState.loading ? "true" : "false"}">
      <header class="tabular-workspace-header">
        <div>
          <span class="tabular-eyebrow">TABULAR · XGBOOST</span>
          <h2>${escapeHtml(project.project_name || text("tabular.title", "表格模型", "Tabular models"))}</h2>
          <p>${escapeHtml(text("tabular.subtitle", "以同一份資料契約完成匯入、訓練、推論、版本與交付。", "Import, train, infer, version and deliver with one consistent data contract."))}</p>
        </div>
        <div class="tabular-header-status">
          ${renderStatusBadge(ready ? "ready" : "needs-data", ready ? text("tabular.ready", "可訓練", "Ready") : text("tabular.notReady", "尚未就緒", "Not ready"))}
          ${renderStatusBadge(statusName, trainingStatusLabel(statusName))}
        </div>
      </header>

      ${tabularState.error ? `<div class="tabular-alert error" role="alert">${escapeHtml(localizeServerMessage(tabularState.error))}</div>` : ""}
      ${renderValidationAlert(validation)}

      <nav class="tabular-workspace-tabs" aria-label="${escapeHtml(text("tabular.nav.label", "表格工作區功能", "Tabular workspace sections"))}">
        ${renderPanelButton("overview", "fa-table-columns", text("tabular.nav.overview", "總覽", "Overview"))}
        ${renderPanelButton("data", "fa-file-csv", text("tabular.nav.data", "資料與欄位", "Data & schema"))}
        ${renderPanelButton("training", "fa-chart-line", text("tabular.nav.training", "訓練", "Training"))}
        ${renderPanelButton("inference", "fa-bolt", text("tabular.nav.inference", "推論", "Inference"))}
        ${renderPanelButton("registry", "fa-code-branch", text("tabular.nav.registry", "模型版本", "Model versions"))}
        ${renderPanelButton("export", "fa-box", text("tabular.nav.export", "匯出", "Export"))}
      </nav>

      <div class="tabular-panel ${tabularState.panel === "overview" ? "active" : ""}" data-tabular-panel="overview">
        ${renderOverviewPanel(inspection, status, ready)}
      </div>
      <div class="tabular-panel ${tabularState.panel === "data" ? "active" : ""}" data-tabular-panel="data">
        ${renderDataPanel(workspace)}
      </div>
      <div class="tabular-panel ${tabularState.panel === "training" ? "active" : ""}" data-tabular-panel="training">
        ${renderTrainingPanel(status, ready)}
      </div>
      <div class="tabular-panel ${tabularState.panel === "inference" ? "active" : ""}" data-tabular-panel="inference">
        ${renderInferencePanel()}
      </div>
      <div class="tabular-panel ${tabularState.panel === "registry" ? "active" : ""}" data-tabular-panel="registry">
        ${renderRegistryPanel()}
      </div>
      <div class="tabular-panel ${tabularState.panel === "export" ? "active" : ""}" data-tabular-panel="export">
        ${renderExportPanel()}
      </div>
    </section>
  `;
}

function renderOverviewPanel(inspection, status, ready) {
  const config = tabularState.workspace?.config || {};
  const latestModel = tabularState.models[0];
  const rows = Number(inspection.row_count || 0);
  const features = config.feature_columns?.length || 0;
  const completedRuns = completedTabularRuns().length;
  return `
    <div class="tabular-summary-grid">
      ${summaryCard("fa-database", text("tabular.summary.rows", "資料列", "Rows"), formatNumber(rows), inspection.filename || text("tabular.summary.noCsv", "尚未匯入 CSV", "No CSV imported"))}
      ${summaryCard("fa-list-check", text("tabular.summary.features", "輸入特徵", "Features"), formatNumber(features), config.target_column ? `${text("tabular.summary.target", "目標", "Target")}: ${config.target_column}` : text("tabular.summary.noTarget", "尚未指定目標欄位", "No target selected"))}
      ${summaryCard("fa-chart-line", text("tabular.summary.runs", "完成訓練", "Completed runs"), formatNumber(completedRuns), trainingStatusLabel(status.status || "idle"))}
      ${summaryCard("fa-cube", text("tabular.summary.models", "可用模型", "Available models"), formatNumber(tabularState.models.length), latestModel ? `${latestModel.run_id} · ${formatMetric(latestModel.primary_metric_value)}` : text("tabular.summary.noModel", "尚未產生模型", "No model produced"))}
    </div>
    <div class="tabular-overview-grid">
      <article class="tabular-card tabular-workflow-card">
        <div class="tabular-card-head">
          <div><span>${escapeHtml(text("tabular.workflow.title", "生產流程", "Production workflow"))}</span><strong>${escapeHtml(ready ? text("tabular.workflow.ready", "資料契約已就緒", "Data contract ready") : text("tabular.workflow.setup", "先完成資料設定", "Complete data setup first"))}</strong></div>
        </div>
        <ol class="tabular-workflow-steps">
          ${workflowStep(1, Boolean(inspection.row_count), text("tabular.workflow.import", "匯入 UTF-8 CSV", "Import UTF-8 CSV"))}
          ${workflowStep(2, ready, text("tabular.workflow.schema", "確認特徵、目標與切分", "Confirm features, target and split"))}
          ${workflowStep(3, completedRuns > 0, text("tabular.workflow.train", "訓練 XGBoost 並比較指標", "Train XGBoost and compare metrics"))}
          ${workflowStep(4, Boolean(latestModel), text("tabular.workflow.deliver", "驗證版本、推論與匯出", "Validate, infer and export"))}
        </ol>
        <div class="tabular-actions">
          <button class="btn btn-primary" type="button" data-tabular-action="panel" data-panel="${ready ? "training" : "data"}">${escapeHtml(ready ? text("tabular.action.train", "前往訓練", "Go to training") : text("tabular.action.setup", "設定資料", "Set up data"))}</button>
          <button class="btn btn-secondary" type="button" data-tabular-action="compare">${escapeHtml(text("tabular.action.compare", "比較模型", "Compare models"))}</button>
        </div>
      </article>
      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.context.title", "目前契約", "Current contract"))}</span><strong>${escapeHtml(config.task_head === "regression" ? text("tabular.task.regression", "數值預測", "Regression") : text("tabular.task.classification", "分類", "Classification"))}</strong></div><code>${escapeHtml(config.feature_config_hash || "--")}</code></div>
        <dl class="tabular-contract-list">
          <div><dt>${escapeHtml(text("tabular.context.source", "來源", "Source"))}</dt><dd>${escapeHtml(config.source_file || "--")}</dd></div>
          <div><dt>${escapeHtml(text("tabular.context.target", "目標欄位", "Target column"))}</dt><dd>${escapeHtml(config.target_column || "--")}</dd></div>
          <div><dt>${escapeHtml(text("tabular.context.missing", "缺失值", "Missing values"))}</dt><dd>${escapeHtml(text("tabular.context.median", "僅以訓練集的中位數填補", "Train-only median imputation"))}</dd></div>
          <div><dt>${escapeHtml(text("tabular.context.split", "切分", "Split"))}</dt><dd>${formatPercent(config.train_ratio)} / ${formatPercent(config.val_ratio)} / ${formatPercent(config.test_ratio)} · seed ${escapeHtml(config.seed ?? 42)}</dd></div>
        </dl>
      </article>
    </div>
  `;
}

function renderDataPanel(workspace) {
  const inspection = workspace.inspection || {};
  const headers = inspection.headers || [];
  const profiles = inspection.column_profiles || {};
  const draft = tabularState.configDraft || makeConfigDraft(workspace.config || {});
  const featureSet = new Set(draft.feature_columns || []);
  return `
    <div class="tabular-two-column">
      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.data.importEyebrow", "資料來源", "Data source"))}</span><strong>${escapeHtml(text("tabular.data.importTitle", "匯入 CSV", "Import CSV"))}</strong></div></div>
        <p class="tabular-card-copy">${escapeHtml(text("tabular.data.importHelp", "首版接受 UTF-8 CSV 與數值特徵；原始檔會複製到專案資料夾，不依賴外部絕對路徑。", "The first release accepts UTF-8 CSV and numeric features; source data is copied into the project instead of relying on an external absolute path."))}</p>
        <div class="tabular-file-control">
          <input id="tabular-dataset-file" type="file" accept=".csv,text/csv">
          <button class="btn btn-primary" type="button" data-tabular-action="import-dataset">${escapeHtml(text("tabular.data.importButton", "匯入並檢查", "Import and inspect"))}</button>
        </div>
        ${inspection.row_count ? `
          <div class="tabular-dataset-facts">
            <span><strong>${formatNumber(inspection.row_count)}</strong>${escapeHtml(text("tabular.data.rows", "資料列", "rows"))}</span>
            <span><strong>${formatNumber(inspection.column_count)}</strong>${escapeHtml(text("tabular.data.columns", "欄位", "columns"))}</span>
            <span><strong>${formatNumber(Object.values(profiles).filter((item) => item.is_numeric).length)}</strong>${escapeHtml(text("tabular.data.numeric", "數值欄", "numeric"))}</span>
          </div>
        ` : `<div class="tabular-empty-inline">${escapeHtml(text("tabular.data.empty", "尚未匯入 CSV。", "No CSV has been imported."))}</div>`}
      </article>

      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.schema.eyebrow", "資料契約", "Data contract"))}</span><strong>${escapeHtml(text("tabular.schema.title", "欄位與可重現切分", "Schema and reproducible split"))}</strong></div></div>
        <form id="tabular-config-form" class="tabular-form-stack">
          <div class="tabular-form-grid two">
            ${selectField("tabular-target-column", text("tabular.schema.target", "目標欄位", "Target column"), headers, draft.target_column, true)}
            <label><span>${escapeHtml(text("tabular.schema.task", "任務類型", "Task type"))}</span><select id="tabular-task-head"><option value="classification" ${draft.task_head === "classification" ? "selected" : ""}>${escapeHtml(text("tabular.task.classification", "分類", "Classification"))}</option><option value="regression" ${draft.task_head === "regression" ? "selected" : ""}>${escapeHtml(text("tabular.task.regression", "數值預測", "Regression"))}</option></select></label>
            ${selectField("tabular-id-column", text("tabular.schema.id", "識別欄（選填）", "ID column (optional)"), headers, draft.id_column)}
            ${selectField("tabular-split-column", text("tabular.schema.splitColumn", "既有切分欄（選填）", "Existing split column (optional)"), headers, draft.split_column)}
          </div>
          <fieldset class="tabular-feature-fieldset">
            <legend>${escapeHtml(text("tabular.schema.features", "輸入特徵（首版限數值欄位）", "Input features (numeric columns in this release)"))}</legend>
            <div class="tabular-feature-grid">
              ${headers.length ? headers.map((header) => {
                const profile = profiles[header] || {};
                const disabled = !profile.is_numeric || header === draft.target_column || header === draft.id_column || header === draft.split_column;
                return `<label class="tabular-feature-option ${disabled ? "disabled" : ""}"><input type="checkbox" data-tabular-feature value="${escapeHtml(header)}" ${featureSet.has(header) && !disabled ? "checked" : ""} ${disabled ? "disabled" : ""}><span><strong>${escapeHtml(header)}</strong><small>${profile.is_numeric ? `${formatPercent(1 - Number(profile.missing_ratio || 0))} ${escapeHtml(text("tabular.schema.present", "有效", "present"))}` : escapeHtml(text("tabular.schema.nonNumeric", "非數值", "non-numeric"))}</small></span></label>`;
              }).join("") : `<div class="tabular-empty-inline">${escapeHtml(text("tabular.schema.importFirst", "匯入資料後即可選擇特徵。", "Import data to select features."))}</div>`}
            </div>
          </fieldset>
          <div class="tabular-form-grid four">
            ${numberField("tabular-train-ratio", text("tabular.schema.trainRatio", "訓練比例", "Train ratio"), draft.train_ratio, 0, 1, 0.01)}
            ${numberField("tabular-val-ratio", text("tabular.schema.valRatio", "驗證比例", "Validation ratio"), draft.val_ratio, 0, 1, 0.01)}
            ${numberField("tabular-test-ratio", text("tabular.schema.testRatio", "測試比例", "Test ratio"), draft.test_ratio, 0, 1, 0.01)}
            ${numberField("tabular-seed", text("tabular.schema.seed", "隨機種子", "Random seed"), draft.seed, 0, 2147483647, 1)}
          </div>
          <div class="tabular-actions"><button class="btn btn-primary" type="submit">${escapeHtml(text("tabular.schema.save", "儲存並驗證", "Save and validate"))}</button><span class="tabular-form-note">${escapeHtml(text("tabular.schema.ratioHelp", "比例總和必須為 1；分類任務會採可重現分層切分。", "Ratios must total 1; classification uses reproducible stratified splitting."))}</span></div>
        </form>
      </article>
    </div>
    ${renderColumnProfiles(inspection)}
    ${renderPreviewTable(inspection)}
  `;
}

function renderTrainingPanel(status, ready) {
  const draft = tabularState.trainingDraft || {};
  const active = ACTIVE_TRAINING_STATUSES.has(String(status.status || ""));
  const latestMetric = lastItem(status.metrics || []);
  const bestMetrics = tabularState.runMetrics?.best_metrics || latestMetric || {};
  return `
    <div class="tabular-training-layout">
      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.training.engine", "獨立後台", "Independent backend"))}</span><strong>${escapeHtml(text("tabular.training.backendName", "獨立 Tabular XGBoost 後台", "TabularXGBoostBackend"))}</strong></div>${renderStatusBadge(status.status || "idle", trainingStatusLabel(status.status || "idle"))}</div>
        <div class="tabular-engine-note"><i class="fa-solid fa-shield-halved" aria-hidden="true"></i><span>${escapeHtml(text("tabular.training.isolation", "此工作區使用獨立的 xgboost_tabular 後台，不會改寫既有 RNN XGBoost 流程。", "This workspace uses the independent xgboost_tabular backend and does not rewrite the existing RNN XGBoost flow."))}</span></div>
        <form id="tabular-training-form" class="tabular-form-stack">
          <div class="tabular-form-grid three">
            <label><span>${escapeHtml(text("tabular.training.runId", "Run ID（選填）", "Run ID (optional)"))}</span><input id="tabular-train-run-id" value="${escapeHtml(draft.runId || "")}" placeholder="run_tabular_..."></label>
            ${numberField("tabular-train-epochs", text("tabular.training.rounds", "提升迭代輪數", "Boosting rounds"), draft.epochs ?? 100, 1, 5000, 1)}
            ${numberField("tabular-train-learning-rate", text("tabular.training.learningRate", "學習率", "Learning rate"), draft.learningRate ?? 0.05, 0.0001, 1, 0.001)}
            ${numberField("tabular-train-max-depth", text("tabular.training.maxDepth", "樹最大深度", "Max depth"), draft.maxDepth ?? 4, 1, 32, 1)}
            ${numberField("tabular-train-subsample", text("tabular.training.subsample", "資料抽樣比例", "Subsample"), draft.subsample ?? 1, 0.1, 1, 0.05)}
            ${numberField("tabular-train-colsample", text("tabular.training.colsample", "特徵抽樣比例", "Column sample"), draft.colsampleBytree ?? 1, 0.1, 1, 0.05)}
          </div>
          <div class="tabular-actions">
            <button class="btn btn-primary" type="submit" ${!ready || active ? "disabled" : ""}>${escapeHtml(text("tabular.training.start", "開始訓練", "Start training"))}</button>
            <button class="btn btn-secondary" type="button" data-tabular-action="stop-training" ${active ? "" : "disabled"}>${escapeHtml(text("tabular.training.stop", "停止訓練", "Stop training"))}</button>
            <button class="btn btn-ghost" type="button" data-tabular-action="refresh-training">${escapeHtml(text("tabular.training.refresh", "重新整理", "Refresh"))}</button>
          </div>
        </form>
      </article>
      <article class="tabular-card tabular-monitor-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.monitor.title", "訓練狀態", "Training status"))}</span><strong>${escapeHtml(status.run_id || text("tabular.monitor.noRun", "尚無執行中的訓練", "No active run"))}</strong></div><span>${Number(status.epoch || 0)} / ${Number(status.total_epochs || 0)}</span></div>
        ${renderTrainingProgress(status)}
        ${status.error ? `<div class="tabular-alert error">${escapeHtml(localizeServerMessage(status.error))}</div>` : ""}
        <div class="tabular-metric-grid">
          ${metricCell("Macro-F1", bestMetrics["val/macro_f1"])}
          ${metricCell("Accuracy", bestMetrics["val/accuracy"])}
          ${metricCell("MAE", bestMetrics["val/mae"])}
          ${metricCell("R²", bestMetrics["val/r2"])}
          ${metricCell("RMSE", bestMetrics["val/rmse"])}
          ${metricCell(text("tabular.monitor.loss", "驗證損失", "Validation loss"), bestMetrics["val/loss"])}
        </div>
      </article>
    </div>
  `;
}

function renderInferencePanel() {
  const models = tabularState.models;
  const hasModel = models.length > 0;
  return `
    <div class="tabular-two-column">
      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.inference.singleEyebrow", "驗收測試", "Acceptance test"))}</span><strong>${escapeHtml(text("tabular.inference.singleTitle", "單筆推論", "Single-row inference"))}</strong></div></div>
        ${modelSelect("tabular-inference-model", models, tabularState.selectedModelId, text("tabular.inference.model", "使用模型", "Model"))}
        <label class="tabular-json-field"><span>${escapeHtml(text("tabular.inference.row", "JSON 特徵列", "JSON feature row"))}</span><textarea id="tabular-row-json" rows="10" spellcheck="false">${escapeHtml(tabularState.rowDraft || "{}")}</textarea></label>
        <div class="tabular-actions"><button class="btn btn-primary" type="button" data-tabular-action="infer-row" ${hasModel ? "" : "disabled"}>${escapeHtml(text("tabular.inference.run", "執行推論", "Run inference"))}</button></div>
        ${renderRowResult(tabularState.rowResult)}
      </article>
      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.inference.batchEyebrow", "交付檢查", "Delivery check"))}</span><strong>${escapeHtml(text("tabular.inference.batchTitle", "批次 CSV 推論", "Batch CSV inference"))}</strong></div></div>
        <p class="tabular-card-copy">${escapeHtml(text("tabular.inference.batchHelp", "上傳含完整特徵欄位的 CSV；結果會保留原欄位並附加預測值。", "Upload a CSV containing all required feature columns; the result keeps original columns and appends predictions."))}</p>
        <div class="tabular-file-control vertical"><input id="tabular-batch-file" type="file" accept=".csv,text/csv"><button class="btn btn-primary" type="button" data-tabular-action="infer-batch" ${hasModel ? "" : "disabled"}>${escapeHtml(text("tabular.inference.batchRun", "執行批次推論", "Run batch inference"))}</button></div>
        ${renderBatchResult(tabularState.batchResult)}
      </article>
    </div>
    <article class="tabular-card">
      <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.inference.contractEyebrow", "輸入契約", "Input contract"))}</span><strong>${escapeHtml(text("tabular.inference.contractTitle", "模型要求的欄位順序", "Required model feature order"))}</strong></div></div>
      <div class="tabular-feature-chips">${(tabularState.workspace?.config?.feature_columns || []).map((column, index) => `<span><b>${index + 1}</b>${escapeHtml(column)}</span>`).join("") || `<span>${escapeHtml(text("tabular.inference.noFeatures", "尚未設定特徵欄位", "No feature columns configured"))}</span>`}</div>
    </article>
  `;
}

function renderRegistryPanel() {
  const versions = tabularState.versions;
  return `
    <article class="tabular-card">
      <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.registry.eyebrow", "模型治理", "Model governance"))}</span><strong>${escapeHtml(text("tabular.registry.title", "版本與生命週期", "Versions and lifecycle"))}</strong></div><button class="btn btn-secondary btn-sm" type="button" data-tabular-action="refresh-registry">${escapeHtml(text("tabular.common.refresh", "重新整理", "Refresh"))}</button></div>
      <div class="tabular-lifecycle-flow"><span>${escapeHtml(text("tabular.lifecycle.pending", "待驗證", "Pending validation"))}</span><i class="fa-solid fa-arrow-right"></i><span>${escapeHtml(text("tabular.lifecycle.validated", "已驗證", "Validated"))}</span><i class="fa-solid fa-arrow-right"></i><span>${escapeHtml(text("tabular.lifecycle.production", "正式模型", "Production"))}</span><i class="fa-solid fa-arrow-right"></i><span>${escapeHtml(text("tabular.lifecycle.retired", "已淘汰", "Retired"))}</span></div>
      <div class="tabular-version-list">
        ${versions.length ? versions.map(renderVersionCard).join("") : `<div class="tabular-empty-inline">${escapeHtml(text("tabular.registry.empty", "完成訓練後，best.json 會自動登錄為待驗證版本。", "After training, best.json is automatically registered as a pending-validation version."))}</div>`}
      </div>
    </article>
  `;
}

function renderExportPanel() {
  const runs = completedTabularRuns();
  const selected = tabularState.selectedExportRunId;
  const result = tabularState.exportResult || tabularState.exports[0] || null;
  return `
    <div class="tabular-two-column">
      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.export.eyebrow", "模型交付", "Model delivery"))}</span><strong>${escapeHtml(text("tabular.export.title", "建立 Tabular 模型包", "Build Tabular model package"))}</strong></div></div>
        <p class="tabular-card-copy">${escapeHtml(text("tabular.export.help", "模型包會一起包含 XGBoost JSON、特徵結構、缺失值規則、標籤編碼、指標、契約與雜湊。", "The package includes XGBoost JSON, feature schema, imputation rules, label encoding, metrics, contracts and checksums."))}</p>
        <label><span>${escapeHtml(text("tabular.export.run", "選擇完成的 Run", "Completed run"))}</span><select id="tabular-export-run"><option value="">${escapeHtml(text("tabular.export.select", "選擇 Run", "Select a run"))}</option>${runs.map((run) => `<option value="${escapeHtml(run.run_id)}" ${run.run_id === selected ? "selected" : ""}>${escapeHtml(run.run_id)} · ${escapeHtml(run.primary_metric_name || "metric")} ${formatMetric(run.primary_metric_value)}</option>`).join("")}</select></label>
        <div class="tabular-actions"><button class="btn btn-primary" type="button" data-tabular-action="export" ${selected ? "" : "disabled"}>${escapeHtml(text("tabular.export.button", "產生交付包", "Build delivery package"))}</button></div>
      </article>
      <article class="tabular-card">
        <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.export.resultEyebrow", "最近結果", "Latest result"))}</span><strong>${escapeHtml(text("tabular.export.resultTitle", "匯出產物", "Export artifact"))}</strong></div></div>
        ${result ? renderExportResult(result) : `<div class="tabular-empty-inline">${escapeHtml(text("tabular.export.empty", "尚未建立 Tabular 匯出包。", "No Tabular package has been created."))}</div>`}
      </article>
    </div>
    <article class="tabular-card">
      <div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.export.historyEyebrow", "稽核紀錄", "Audit history"))}</span><strong>${escapeHtml(text("tabular.export.historyTitle", "最近匯出", "Recent exports"))}</strong></div></div>
      <div class="tabular-export-history">${tabularState.exports.length ? tabularState.exports.map((item) => `<div><span class="tabular-status success">${escapeHtml(String(item.export_type || "package").replaceAll("_", " "))}</span><strong>${escapeHtml(item.run_id || item.export_id || "--")}</strong><code>${escapeHtml(exportPath(item))}</code><small>${escapeHtml(formatDate(item.created_at))}</small></div>`).join("") : `<div class="tabular-empty-inline">${escapeHtml(text("tabular.export.noHistory", "沒有匯出紀錄。", "No export history."))}</div>`}</div>
    </article>
  `;
}

function handleWorkspaceClick(event) {
  const panelButton = event.target instanceof Element ? event.target.closest("[data-tabular-panel-select]") : null;
  if (panelButton) {
    setTabularPanel(panelButton.dataset.tabularPanelSelect);
    return;
  }
  const action = event.target instanceof Element ? event.target.closest("[data-tabular-action]") : null;
  if (!action) return;
  const name = action.dataset.tabularAction;
  if (name === "panel") setTabularPanel(action.dataset.panel);
  else if (name === "dashboard") eventBus.emit("navigate", "dashboard");
  else if (name === "projects") eventBus.emit("navigate", "projects");
  else if (name === "compare") {
    eventBus.emit("set-compare-architecture", "tabular");
    eventBus.emit("navigate", "model-compare");
  } else if (name === "import-dataset") void importDataset();
  else if (name === "stop-training") void stopTraining();
  else if (name === "refresh-training") void refreshTrainingStatus({ loadMetrics: true });
  else if (name === "infer-row") void runRowInference();
  else if (name === "infer-batch") void runBatchInference();
  else if (name === "download-batch") void downloadBatchResult();
  else if (name === "refresh-registry") void refreshModelsAndVersions();
  else if (name === "lifecycle") void transitionLifecycle(action.dataset.modelId, action.dataset.status);
  else if (name === "export") void exportTabularPackage();
}

function handleWorkspaceSubmit(event) {
  if (event.target?.id === "tabular-config-form") {
    event.preventDefault();
    captureWorkspaceDraft();
    void saveTabularConfig().catch((error) => {
      tabularState.error = error.message;
      renderTabularWorkspace();
    });
  } else if (event.target?.id === "tabular-training-form") {
    event.preventDefault();
    captureWorkspaceDraft();
    void startTraining();
  }
}

function captureWorkspaceDraft(event) {
  const root = tabularState.root;
  if (!root) return;
  const configForm = root.querySelector("#tabular-config-form");
  if (configForm) {
    tabularState.configDraft = {
      ...(tabularState.configDraft || {}),
      source_file: tabularState.workspace?.config?.source_file || "",
      feature_columns: [...configForm.querySelectorAll("[data-tabular-feature]:checked")].map((item) => item.value),
      target_column: root.querySelector("#tabular-target-column")?.value || "",
      id_column: root.querySelector("#tabular-id-column")?.value || "",
      split_column: root.querySelector("#tabular-split-column")?.value || "",
      task_head: root.querySelector("#tabular-task-head")?.value || "classification",
      train_ratio: numberOr(root.querySelector("#tabular-train-ratio")?.value, 0.7),
      val_ratio: numberOr(root.querySelector("#tabular-val-ratio")?.value, 0.15),
      test_ratio: numberOr(root.querySelector("#tabular-test-ratio")?.value, 0.15),
      seed: numberOr(root.querySelector("#tabular-seed")?.value, 42),
      missing_strategy: "median",
    };
  }
  const trainingForm = root.querySelector("#tabular-training-form");
  if (trainingForm) {
    tabularState.trainingDraft = {
      runId: root.querySelector("#tabular-train-run-id")?.value?.trim() || "",
      epochs: numberOr(root.querySelector("#tabular-train-epochs")?.value, 100),
      learningRate: numberOr(root.querySelector("#tabular-train-learning-rate")?.value, 0.05),
      maxDepth: numberOr(root.querySelector("#tabular-train-max-depth")?.value, 4),
      subsample: numberOr(root.querySelector("#tabular-train-subsample")?.value, 1),
      colsampleBytree: numberOr(root.querySelector("#tabular-train-colsample")?.value, 1),
    };
  }
  const rowJson = root.querySelector("#tabular-row-json");
  if (rowJson) tabularState.rowDraft = rowJson.value;
  const modelSelectEl = root.querySelector("#tabular-inference-model");
  if (modelSelectEl) tabularState.selectedModelId = modelSelectEl.value;
  const exportSelectEl = root.querySelector("#tabular-export-run");
  if (exportSelectEl) tabularState.selectedExportRunId = exportSelectEl.value;

  const changedId = event?.type === "change" ? String(event.target?.id || "") : "";
  if (["tabular-target-column", "tabular-id-column", "tabular-split-column"].includes(changedId)) {
    const excluded = new Set([
      tabularState.configDraft?.target_column,
      tabularState.configDraft?.id_column,
      tabularState.configDraft?.split_column,
    ].filter(Boolean));
    tabularState.configDraft.feature_columns = (tabularState.configDraft.feature_columns || []).filter((column) => !excluded.has(column));
    renderTabularWorkspace();
  } else if (changedId === "tabular-export-run") {
    renderTabularWorkspace();
  }
}

async function importDataset() {
  const file = tabularState.root?.querySelector("#tabular-dataset-file")?.files?.[0];
  if (!file) {
    toast(text("tabular.toast.chooseCsv", "請先選擇 CSV 檔案。", "Choose a CSV file first."));
    return;
  }
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const result = await apiUpload(`/api/projects/${appState.currentProjectId}/tabular/dataset/import`, { method: "POST", body: form });
    tabularState.workspace = result;
    tabularState.configDraft = makeConfigDraft(result.config || {});
    tabularState.error = "";
    toast(text("tabular.toast.imported", "CSV 已匯入並完成欄位檢查。", "CSV imported and inspected."));
    renderTabularWorkspace();
    eventBus.emit("refresh-project");
  } catch (error) {
    tabularState.error = error.message;
    renderTabularWorkspace();
  }
}

async function saveTabularConfig({ quiet = false } = {}) {
  captureWorkspaceDraft();
  const projectId = appState.currentProjectId;
  if (!projectId) throw new Error("Project not selected");
  const result = await apiFetch(`/api/projects/${projectId}/tabular/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(tabularState.configDraft || {}),
  });
  tabularState.workspace = result;
  tabularState.configDraft = makeConfigDraft(result.config || {});
  tabularState.error = "";
  renderTabularWorkspace();
  if (!quiet) toast(result.validation?.valid
    ? text("tabular.toast.configSaved", "資料契約已儲存，可開始訓練。", "Data contract saved; training is ready.")
    : text("tabular.toast.configInvalid", "資料契約已儲存，但仍有需要修正的項目。", "Data contract saved, but some issues still need attention."));
  return result;
}

async function startTraining() {
  try {
    const saved = await saveTabularConfig({ quiet: true });
    if (!saved.validation?.valid) throw new Error((saved.validation?.errors || []).join(" ") || "Tabular dataset is not ready.");
    const draft = tabularState.trainingDraft || {};
    const taskHead = saved.config?.task_head || "classification";
    const payload = {
      model: taskHead === "regression" ? "xgboost_regressor" : "xgboost_classifier",
      epochs: Math.trunc(numberOr(draft.epochs, 100)),
      batch_size: 0,
      imgsz: 0,
      lr0: numberOr(draft.learningRate, 0.05),
      lr0_mode: "custom",
      device: "cpu",
      patience: 20,
      workers: 0,
      workers_mode: "custom",
      cache: false,
      amp: false,
      seed: Math.trunc(numberOr(saved.config?.seed, 42)),
      save_period: 0,
      close_mosaic: 0,
      optimizer: "xgboost",
      backend: "xgboost_tabular",
      task_head: taskHead,
      learning_rate: numberOr(draft.learningRate, 0.05),
      max_depth: Math.trunc(numberOr(draft.maxDepth, 4)),
      subsample: numberOr(draft.subsample, 1),
      colsample_bytree: numberOr(draft.colsampleBytree, 1),
    };
    if (draft.runId) payload.run_id = draft.runId;
    const result = await apiFetch(`/api/projects/${appState.currentProjectId}/train/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    tabularState.status = {
      status: "training",
      architecture: "tabular",
      backend: "xgboost_tabular",
      run_id: result.run_id || payload.run_id || "",
      epoch: 0,
      total_epochs: payload.epochs,
      metrics: [],
      error: "",
    };
    appState.trainingStatus = tabularState.status;
    tabularState.runMetrics = null;
    tabularState.runMetricsId = "";
    tabularState.trainingDraft.runId = "";
    toast(text("tabular.toast.trainingStarted", "Tabular XGBoost 訓練已開始。", "Tabular XGBoost training started."));
    renderTabularWorkspace();
    scheduleStatusPoll(500);
  } catch (error) {
    tabularState.error = error.message;
    renderTabularWorkspace();
  }
}

async function stopTraining() {
  try {
    await apiFetch(`/api/projects/${appState.currentProjectId}/train/stop`, { method: "POST" });
    tabularState.status = { ...(tabularState.status || {}), status: "stopping" };
    toast(text("tabular.toast.stopSent", "已送出停止訓練要求。", "Stop request sent."));
    renderTabularWorkspace();
    scheduleStatusPoll(500);
  } catch (error) {
    tabularState.error = error.message;
    renderTabularWorkspace();
  }
}

async function refreshTrainingStatus({ loadMetrics = false } = {}) {
  if (tabularState.polling || !appState.currentProjectId) return;
  tabularState.polling = true;
  try {
    const previous = String(tabularState.status?.status || "");
    tabularState.status = await apiFetch(`/api/projects/${appState.currentProjectId}/train/status`, { dedupe: false });
    appState.trainingStatus = tabularState.status;
    const current = String(tabularState.status?.status || "");
    if (["overview", "training"].includes(tabularState.panel)) renderTabularWorkspace();
    if (loadMetrics || TERMINAL_TRAINING_STATUSES.has(current)) await loadLatestRunMetrics();
    if (TERMINAL_TRAINING_STATUSES.has(current) && (!TERMINAL_TRAINING_STATUSES.has(previous) || tabularState.lastTerminalRunId !== tabularState.status?.run_id)) {
      tabularState.lastTerminalRunId = tabularState.status?.run_id || "";
      await refreshModelsAndVersions({ render: false });
      eventBus.emit("refresh-project");
      renderTabularWorkspace();
    }
  } catch (error) {
    console.warn("Failed to refresh Tabular training status", error);
  } finally {
    tabularState.polling = false;
    updatePollingForStatus();
  }
}

async function loadLatestRunMetrics() {
  const runId = tabularState.status?.run_id || completedTabularRuns()[0]?.run_id || tabularState.models[0]?.run_id || "";
  if (!runId || (tabularState.runMetricsId === runId && tabularState.runMetrics)) return;
  try {
    tabularState.runMetrics = await apiFetch(`/api/projects/${appState.currentProjectId}/train/runs/${encodeURIComponent(runId)}/metrics`, { dedupe: false });
    tabularState.runMetricsId = runId;
    if (["overview", "training"].includes(tabularState.panel)) renderTabularWorkspace();
  } catch (error) {
    if (error?.status !== 404) console.warn("Failed to load Tabular metrics", error);
  }
}

function updatePollingForStatus() {
  if (appState.currentPage !== "tabular" || !ACTIVE_TRAINING_STATUSES.has(String(tabularState.status?.status || ""))) {
    stopStatusPolling();
    return;
  }
  scheduleStatusPoll(1500);
}

function scheduleStatusPoll(delay) {
  if (tabularState.pollingTimer) return;
  tabularState.pollingTimer = window.setTimeout(() => {
    tabularState.pollingTimer = null;
    void refreshTrainingStatus();
  }, delay);
}

function stopStatusPolling() {
  if (tabularState.pollingTimer) window.clearTimeout(tabularState.pollingTimer);
  tabularState.pollingTimer = null;
}

async function runRowInference() {
  captureWorkspaceDraft();
  try {
    const row = JSON.parse(tabularState.rowDraft || "{}");
    if (!row || Array.isArray(row) || typeof row !== "object") throw new Error(text("tabular.inference.rowObject", "單筆推論必須是 JSON 物件。", "Single-row inference requires a JSON object."));
    tabularState.rowResult = await apiFetch(`/api/projects/${appState.currentProjectId}/tabular/inference/row`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ row, model_id: tabularState.selectedModelId || null }),
    });
    tabularState.error = "";
    renderTabularWorkspace();
  } catch (error) {
    tabularState.error = error instanceof SyntaxError
      ? text("tabular.inference.invalidJson", "JSON 格式不正確，請檢查欄位名稱與數值。", "Invalid JSON; check feature names and values.")
      : error.message;
    renderTabularWorkspace();
  }
}

async function runBatchInference() {
  captureWorkspaceDraft();
  const file = tabularState.root?.querySelector("#tabular-batch-file")?.files?.[0];
  if (!file) {
    toast(text("tabular.toast.chooseBatch", "請先選擇批次推論 CSV。", "Choose a batch inference CSV first."));
    return;
  }
  const form = new FormData();
  form.append("file", file, file.name);
  const params = new URLSearchParams();
  if (tabularState.selectedModelId) params.set("model_id", tabularState.selectedModelId);
  try {
    tabularState.batchResult = await apiUpload(`/api/projects/${appState.currentProjectId}/tabular/inference/batch?${params}`, { method: "POST", body: form });
    tabularState.error = "";
    renderTabularWorkspace();
  } catch (error) {
    tabularState.error = error.message;
    renderTabularWorkspace();
  }
}

async function downloadBatchResult() {
  const url = tabularState.batchResult?.download_url;
  if (!url) return;
  try {
    const blob = await apiFetchBlob(url);
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${tabularState.batchResult.job_id || "tabular"}_predictions.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (error) {
    tabularState.error = error.message;
    renderTabularWorkspace();
  }
}

async function refreshModelsAndVersions({ render = true } = {}) {
  const projectId = appState.currentProjectId;
  if (!projectId) return;
  const [modelsResult, versionsResult] = await Promise.allSettled([
    apiFetch(`/api/projects/${projectId}/models?scope=all`, { dedupe: false }),
    apiFetch(`/api/projects/${projectId}/models/versions`, { dedupe: false }),
  ]);
  if (modelsResult.status === "fulfilled") tabularState.models = normalizeModels(modelsResult.value);
  if (versionsResult.status === "fulfilled") tabularState.versions = normalizeVersions(versionsResult.value);
  ensureSelections();
  if (render) renderTabularWorkspace();
}

async function transitionLifecycle(modelId, status) {
  if (!modelId || !status) return;
  try {
    await apiFetch(`/api/projects/${appState.currentProjectId}/models/${encodeURIComponent(modelId)}/lifecycle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status, limitations: [] }),
    });
    toast(text("tabular.toast.lifecycle", "模型生命週期已更新。", "Model lifecycle updated."));
    await refreshModelsAndVersions();
    eventBus.emit("refresh-project");
  } catch (error) {
    tabularState.error = error.message;
    renderTabularWorkspace();
  }
}

async function exportTabularPackage() {
  captureWorkspaceDraft();
  const runId = tabularState.selectedExportRunId;
  if (!runId) return;
  const query = new URLSearchParams({ run_id: runId, format: "tabular_package" });
  try {
    const launch = await apiFetch(`/api/projects/${appState.currentProjectId}/export/jobs?${query}`, { method: "POST", suppressProgress: true });
    tabularState.exportResult = await followServerTask(launch.job_id, { kind: "export", title: text("tabular.export.progress", "匯出 Tabular 模型", "Export Tabular model") });
    const payload = await apiFetch(`/api/projects/${appState.currentProjectId}/exports?limit=12`, { dedupe: false });
    tabularState.exports = normalizeExports(payload);
    tabularState.error = "";
    toast(text("tabular.toast.exported", "Tabular 模型交付包已建立。", "Tabular delivery package created."));
    renderTabularWorkspace();
  } catch (error) {
    tabularState.error = error.message;
    renderTabularWorkspace();
  }
}

function setTabularPanel(panel) {
  if (String(panel || "") === "model-compare") return;
  const next = PANELS.has(String(panel || "")) ? String(panel) : "overview";
  tabularState.panel = next;
  trainingModeState.activeMode = "tabular";
  trainingModeState.activeTabularPanel = next;
  if (appState.currentPage === "tabular") renderTabularWorkspace();
  syncPanelState();
  if (next === "registry") void refreshModelsAndVersions();
  if (next === "training") void refreshTrainingStatus({ loadMetrics: true });
}

function syncPanelState() {
  document.querySelectorAll("[data-tabular-nav]").forEach((button) => {
    button.classList.toggle("active", button.dataset.tabularNav === tabularState.panel && appState.currentPage === "tabular");
  });
}

function completedTabularRuns() {
  const runs = (appState.currentProject?.training_runs || []).filter((run) => run
    && String(run.status || "").toLowerCase() === "completed"
    && (String(run.architecture || "").toLowerCase() === "tabular" || String(run.task_type || "").toLowerCase().startsWith("tabular_")));
  const known = new Set(runs.map((run) => String(run.run_id || "")));
  tabularState.models.forEach((model) => {
    const runId = String(model.run_id || "");
    if (!runId || known.has(runId)) return;
    runs.push({
      run_id: runId,
      status: "completed",
      architecture: "tabular",
      task_type: model.task_type,
      model: model.model_name,
      completed_at: model.created_at,
      primary_metric_name: model.primary_metric_name,
      primary_metric_value: model.primary_metric_value,
    });
    known.add(runId);
  });
  return [...runs].sort((a, b) => String(b.completed_at || "").localeCompare(String(a.completed_at || "")));
}

function normalizeModels(payload) {
  const models = Array.isArray(payload) ? payload : [];
  return models.filter((model) => {
    const isTabular = String(model.architecture || "").toLowerCase() === "tabular"
      || String(model.backend || "").toLowerCase() === "xgboost_tabular"
      || String(model.task_type || "").toLowerCase().startsWith("tabular_");
    const artifactRole = String(model.weight_type || model.artifact_role || "").toLowerCase();
    // Tabular inference currently resolves a selected run to weights/best.json.
    // Keep historical `last` checkpoints in the registry API, but never present
    // one as a selectable model when the runtime would execute `best` instead.
    return isTabular && (!artifactRole || artifactRole === "best");
  });
}

function normalizeVersions(payload) {
  const versions = Array.isArray(payload?.versions) ? payload.versions : [];
  return versions.filter((version) => String(version.architecture || "").toLowerCase() === "tabular"
    || String(version.backend || "").toLowerCase() === "xgboost_tabular"
    || String(version.task_type || "").toLowerCase().startsWith("tabular_"));
}

function normalizeExports(payload) {
  const exports = Array.isArray(payload?.exports) ? payload.exports : [];
  return exports.filter((item) => String(item.export_type || "").toLowerCase().startsWith("tabular_"));
}

function isTabularProject(project) {
  const task = String(project?.task_type || "").toLowerCase();
  const architecture = String(project?.architecture || project?.training_config?.architecture || "").toLowerCase();
  return architecture === "tabular" || task.startsWith("tabular_");
}

function makeConfigDraft(config) {
  return {
    source_file: String(config.source_file || ""),
    feature_columns: [...(config.feature_columns || [])],
    target_column: String(config.target_column || ""),
    id_column: String(config.id_column || ""),
    split_column: String(config.split_column || ""),
    task_head: config.task_head === "regression" ? "regression" : "classification",
    train_ratio: numberOr(config.train_ratio, 0.7),
    val_ratio: numberOr(config.val_ratio, 0.15),
    test_ratio: numberOr(config.test_ratio, 0.15),
    seed: numberOr(config.seed, 42),
    missing_strategy: "median",
  };
}

function renderPanelButton(panel, icon, label) {
  return `<button type="button" class="${tabularState.panel === panel ? "active" : ""}" data-tabular-panel-select="${panel}"><i class="fa-solid ${icon}" aria-hidden="true"></i><span>${escapeHtml(label)}</span></button>`;
}

function renderEmptyState(title, body) {
  return `<div class="tabular-empty-state"><i class="fa-solid fa-table-columns" aria-hidden="true"></i><strong>${escapeHtml(title)}</strong><p>${escapeHtml(body)}</p><div class="tabular-actions"><button class="btn btn-primary" type="button" data-tabular-action="projects">${escapeHtml(text("tabular.empty.projects", "建立／開啟 Tabular 專案", "Create or open a Tabular project"))}</button><button class="btn btn-secondary" type="button" data-tabular-action="dashboard">${escapeHtml(text("tabular.empty.dashboard", "返回功能總覽", "Back to dashboard"))}</button></div></div>`;
}

function renderValidationAlert(validation) {
  const errors = validation?.errors || [];
  const warnings = validation?.warnings || [];
  if (!errors.length && !warnings.length) return "";
  const severity = errors.length ? "error" : "warning";
  const items = [...errors, ...warnings];
  return `<div class="tabular-alert ${severity}" role="${errors.length ? "alert" : "status"}"><i class="fa-solid ${errors.length ? "fa-circle-exclamation" : "fa-triangle-exclamation"}" aria-hidden="true"></i><div><strong>${escapeHtml(errors.length ? text("tabular.validation.fix", "資料契約需要修正", "Data contract needs attention") : text("tabular.validation.warning", "資料品質提醒", "Data quality notice"))}</strong><ul>${items.map((item) => `<li>${escapeHtml(localizeServerMessage(item))}</li>`).join("")}</ul></div></div>`;
}

function summaryCard(icon, label, value, caption) {
  return `<article class="tabular-summary-card"><i class="fa-solid ${icon}" aria-hidden="true"></i><div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(caption)}</small></div></article>`;
}

function workflowStep(number, complete, label) {
  return `<li class="${complete ? "complete" : ""}"><span>${complete ? '<i class="fa-solid fa-check"></i>' : number}</span><strong>${escapeHtml(label)}</strong></li>`;
}

function selectField(id, label, values, selected, required = false) {
  return `<label><span>${escapeHtml(label)}</span><select id="${id}" ${required ? "required" : ""}><option value="">${escapeHtml(required ? text("tabular.select.required", "請選擇", "Select") : text("tabular.select.none", "不使用", "None"))}</option>${values.map((value) => `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(value)}</option>`).join("")}</select></label>`;
}

function numberField(id, label, value, min, max, step) {
  return `<label><span>${escapeHtml(label)}</span><input id="${id}" type="number" value="${escapeHtml(value)}" min="${min}" max="${max}" step="${step}" required></label>`;
}

function renderColumnProfiles(inspection) {
  const headers = inspection.headers || [];
  const profiles = inspection.column_profiles || {};
  if (!headers.length) return "";
  return `<article class="tabular-card"><div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.profile.eyebrow", "資料品質", "Data quality"))}</span><strong>${escapeHtml(text("tabular.profile.title", "欄位檢查", "Column profile"))}</strong></div></div><div class="tabular-profile-grid">${headers.map((header) => {
    const profile = profiles[header] || {};
    return `<div><strong>${escapeHtml(header)}</strong><span>${escapeHtml(profile.is_numeric ? text("tabular.profile.numeric", "數值", "Numeric") : text("tabular.profile.text", "文字／類別", "Text / category"))}</span><span>${escapeHtml(text("tabular.profile.missing", "缺失", "Missing"))}: ${formatPercent(profile.missing_ratio)}</span><span>${escapeHtml(text("tabular.profile.distinct", "相異值", "Distinct"))}: ${formatNumber(profile.distinct_count)}</span></div>`;
  }).join("")}</div></article>`;
}

function renderPreviewTable(inspection) {
  const headers = inspection.headers || [];
  const rows = inspection.preview_rows || [];
  if (!headers.length || !rows.length) return "";
  return `<article class="tabular-card"><div class="tabular-card-head"><div><span>${escapeHtml(text("tabular.preview.eyebrow", "安全預覽", "Safe preview"))}</span><strong>${escapeHtml(text("tabular.preview.title", "前 20 筆資料", "First 20 rows"))}</strong></div></div><div class="tabular-table-scroll"><table class="tabular-table"><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((header) => `<td>${escapeHtml(row[header] || "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div></article>`;
}

function renderTrainingProgress(status) {
  const current = Number(status.epoch || 0);
  const total = Number(status.total_epochs || 0);
  const percent = total > 0 ? Math.max(0, Math.min(100, (current / total) * 100)) : 0;
  return `<div class="tabular-training-progress"><div><span>${escapeHtml(trainingStatusLabel(status.status || "idle"))}</span><strong>${Math.round(percent)}%</strong></div><div class="tabular-progress-track"><span style="width:${percent}%"></span></div><small>${escapeHtml(formatDate(status.updated_at || status.completed_at || status.started_at))}</small></div>`;
}

function metricCell(label, value) {
  return `<div><span>${escapeHtml(label)}</span><strong>${formatMetric(value)}</strong></div>`;
}

function modelSelect(id, models, selected, label) {
  return `<label><span>${escapeHtml(label)}</span><select id="${id}" ${models.length ? "" : "disabled"}><option value="">${escapeHtml(text("tabular.model.select", "選擇模型", "Select model"))}</option>${models.map((model) => `<option value="${escapeHtml(model.model_id)}" ${model.model_id === selected ? "selected" : ""}>${escapeHtml(model.run_id)} · ${escapeHtml(model.model_name || "XGBoost")} · ${formatMetric(model.primary_metric_value)}</option>`).join("")}</select></label>`;
}

function renderRowResult(result) {
  if (!result) return `<div class="tabular-empty-inline compact">${escapeHtml(text("tabular.inference.noResult", "尚未執行推論。", "No inference result yet."))}</div>`;
  const value = result.predicted_label ?? result.prediction ?? "--";
  return `<div class="tabular-prediction-result"><span>${escapeHtml(text("tabular.inference.prediction", "預測結果", "Prediction"))}</span><strong>${escapeHtml(value)}</strong>${result.confidence != null ? `<b>${formatPercent(result.confidence)} ${escapeHtml(text("tabular.inference.confidence", "信心度", "confidence"))}</b>` : ""}<small>${formatMetric(result.latency_ms)} ms · ${escapeHtml(result.run_id || "")}</small>${result.probabilities ? `<pre>${escapeHtml(JSON.stringify(result.probabilities, null, 2))}</pre>` : ""}</div>`;
}

function renderBatchResult(result) {
  if (!result) return `<div class="tabular-empty-inline compact">${escapeHtml(text("tabular.inference.noBatch", "尚未執行批次推論。", "No batch inference result yet."))}</div>`;
  return `<div class="tabular-batch-result"><div><span>${escapeHtml(text("tabular.inference.processed", "完成列數", "Rows processed"))}</span><strong>${formatNumber(result.row_count)}</strong></div><div><span>${escapeHtml(text("tabular.inference.latency", "總時間", "Total time"))}</span><strong>${formatMetric(result.total_latency_ms ?? result.latency_ms)} ms</strong></div><button class="btn btn-secondary" type="button" data-tabular-action="download-batch"><i class="fa-solid fa-download"></i>${escapeHtml(text("tabular.inference.download", "下載預測 CSV", "Download prediction CSV"))}</button></div>`;
}

function renderVersionCard(version) {
  const actions = lifecycleActions(version.status || "pending_validation");
  return `<article class="tabular-version-card"><div class="tabular-version-main"><span class="tabular-status ${statusClass(version.status)}">${escapeHtml(lifecycleLabel(version.status))}</span><div><strong>${escapeHtml(version.version || "--")} · ${escapeHtml(version.run_id || "--")}</strong><small>${escapeHtml(version.model_name || "XGBoost")} · ${escapeHtml(version.model_format || "json")} · ${escapeHtml(formatDate(version.created_at))}</small></div></div><div class="tabular-version-metric"><span>${escapeHtml(version.primary_metric_name || "Metric")}</span><strong>${formatMetric(version.primary_metric_value)}</strong></div><div class="tabular-actions compact">${actions.map((action) => `<button class="btn ${action.primary ? "btn-primary" : "btn-secondary"} btn-sm" type="button" data-tabular-action="lifecycle" data-model-id="${escapeHtml(version.model_id)}" data-status="${action.status}">${escapeHtml(action.label)}</button>`).join("")}</div></article>`;
}

function lifecycleActions(status) {
  if (status === "pending_validation") return [
    { status: "validated", label: text("tabular.lifecycle.validate", "標記已驗證", "Mark validated"), primary: true },
    { status: "retired", label: text("tabular.lifecycle.retire", "淘汰", "Retire") },
  ];
  if (status === "validated") return [
    { status: "production", label: text("tabular.lifecycle.promote", "設為正式模型", "Promote to production"), primary: true },
    { status: "retired", label: text("tabular.lifecycle.retire", "淘汰", "Retire") },
  ];
  if (status === "production") return [{ status: "retired", label: text("tabular.lifecycle.retire", "淘汰", "Retire") }];
  return [];
}

function renderExportResult(result) {
  return `<div class="tabular-export-result"><span class="tabular-status success">${escapeHtml(String(result.export_type || "tabular_package").replaceAll("_", " "))}</span><strong>${escapeHtml(result.export_id || result.run_id || "--")}</strong><code>${escapeHtml(exportPath(result))}</code><small>${escapeHtml(formatDate(result.created_at))}</small></div>`;
}

function renderStatusBadge(status, label) {
  return `<span class="tabular-status ${statusClass(status)}">${escapeHtml(label)}</span>`;
}

function statusClass(status) {
  const value = String(status || "").toLowerCase();
  if (["ready", "completed", "production", "validated", "success"].includes(value)) return "success";
  if (["training", "stopping", "pending_validation"].includes(value)) return "active";
  if (["failed", "error"].includes(value)) return "error";
  if (["needs-data", "warning"].includes(value)) return "warning";
  return "neutral";
}

function trainingStatusLabel(status) {
  const labels = {
    idle: ["待命", "Idle"],
    training: ["訓練中", "Training"],
    stopping: ["停止中", "Stopping"],
    stopped: ["已停止", "Stopped"],
    completed: ["已完成", "Completed"],
    failed: ["失敗", "Failed"],
    started: ["已開始", "Started"],
  };
  const pair = labels[String(status || "").toLowerCase()] || [String(status || "--"), String(status || "--")];
  return appState.settings.language === "en" ? pair[1] : pair[0];
}

function lifecycleLabel(status) {
  const labels = {
    pending_validation: ["待驗證", "Pending validation"],
    validated: ["已驗證", "Validated"],
    production: ["正式模型", "Production"],
    retired: ["已淘汰", "Retired"],
  };
  const pair = labels[status] || [status || "--", status || "--"];
  return appState.settings.language === "en" ? pair[1] : pair[0];
}

function exportPath(result) {
  return result.primary_abs_path || result.primary_path || result.package_abs_path || result.package_path || result.summary_path || "--";
}

function text(key, zh, en) {
  const translated = t(key);
  if (translated && translated !== key) return translated;
  return appState.settings.language === "en" ? en : zh;
}

function localizeServerMessage(message) {
  const raw = String(message || "");
  if (appState.settings.language === "en") return raw;
  const exact = {
    "Select a target column that exists in the CSV.": "請選擇 CSV 中存在的目標欄位。",
    "Select at least one numeric feature column.": "請至少選擇一個數值特徵欄位。",
    "Target column cannot also be a feature.": "目標欄位不能同時作為輸入特徵。",
    "Target column contains missing values; targets are never imputed.": "目標欄位含有缺失值；目標值不會自動填補。",
    "Regression target column must contain finite numeric values only.": "數值預測的目標欄位只能包含有限數值。",
    "Classification target column must contain at least two distinct labels.": "分類目標欄位至少需要兩個不同標籤。",
    "Configured split column does not exist in CSV.": "設定的切分欄位不存在於 CSV。",
    "Split column values must be train, val, or test (accepted aliases are training, validation, dev, and testing).": "切分欄位只能使用 train、val 或 test（亦接受 training、validation、dev、testing）。",
    "Provided split column must contain at least one training row.": "既有切分欄位至少需要一筆訓練資料。",
    "Provided split column must contain at least one validation row.": "既有切分欄位至少需要一筆驗證資料。",
    "Train/validation/test ratios must be non-negative and sum to 1; train and validation must be positive.": "訓練、驗證與測試比例不得為負且總和必須為 1；訓練與驗證比例必須大於 0。",
    "Very small datasets may not produce reliable validation metrics.": "資料量過小，驗證指標可能不可靠。",
    "Training stopped by user.": "訓練已由使用者停止。",
    "Tabular dataset is not ready.": "表格資料尚未完成訓練準備。",
  };
  if (exact[raw]) return exact[raw];
  if (raw.startsWith("Feature columns are missing from CSV:")) {
    return `CSV 缺少以下特徵欄位：${raw.slice(raw.indexOf(":") + 1).trim()}`;
  }
  if (raw.startsWith("Tabular MVP accepts numeric features only:")) {
    return `Tabular 首版僅接受數值特徵：${raw.slice(raw.indexOf(":") + 1).trim()}`;
  }
  return raw;
}

function toast(message) {
  eventBus.emit("toast", message);
}

function formatMetric(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (Math.abs(number) >= 1000) return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return number.toFixed(Math.abs(number) < 0.001 && number !== 0 ? 6 : 4).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${(number * 100).toFixed(number * 100 % 1 ? 1 : 0)}%` : "--";
}

function formatNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : "0";
}

function formatDate(value) {
  if (!value) return "--";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function numberOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function lastItem(values) {
  return Array.isArray(values) && values.length ? values[values.length - 1] : null;
}
