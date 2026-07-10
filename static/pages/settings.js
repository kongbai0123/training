import { eventBus } from "../event_bus.js";
import { appState, applyTheme, applyLanguage, t } from "../state.js";
import { apiFetch } from "../api.js";
import { qs, qsa, setHTML, escapeHtml } from "../utils.js";
import { renderModelSetupSettings } from "../core/model_setup.js?v=20260710-model-preparation";

let migrationScan = null;

export function initSettings() {
  qs("#btn-theme-toggle")?.addEventListener("click", () => {
    const nextTheme = appState.settings.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme);
    eventBus.emit("state-changed");
  });

  qs("#settings-language")?.addEventListener("change", (event) => {
    applyLanguage(event.target.value);
    eventBus.emit("state-changed");
  });

  qs("#settings-theme")?.addEventListener("change", (event) => {
    applyTheme(event.target.value);
    eventBus.emit("state-changed");
  });
  qs("#btn-scan-data-migration")?.addEventListener("click", scanProjectDataMigration);
  qs("#btn-apply-data-migration")?.addEventListener("click", applyProjectDataMigration);
}

export function renderSettingsPage() {
  const langSelect = qs("#settings-language");
  if (langSelect) langSelect.value = appState.settings.language;

  const themeSelect = qs("#settings-theme");
  if (themeSelect) themeSelect.value = appState.settings.theme;
  renderProjectDataMigration();
  void renderModelSetupSettings();
}

async function scanProjectDataMigration() {
  const button = qs("#btn-scan-data-migration");
  if (button) button.disabled = true;
  setHTML("#project-data-migration-list", `<div class="empty-state">${escapeHtml(t("settings.scanningLegacy"))}</div>`);
  try {
    migrationScan = await apiFetch("/api/projects/data-migration/scan");
    renderProjectDataMigration();
  } catch (err) {
    setHTML("#project-data-migration-list", `<div class="empty-state">${escapeHtml(t("settings.scanFailed", { message: err.message }))}</div>`);
  } finally {
    if (button) button.disabled = false;
  }
}

async function applyProjectDataMigration() {
  const selected = qsa("[data-migration-project]:checked").map((item) => item.value);
  const deleteSource = Boolean(qs("#migration-delete-source")?.checked);
  if (!selected.length) {
    eventBus.emit("toast", t("settings.selectProjectToMigrate"));
    return;
  }
  if (deleteSource) {
    const confirmed = window.confirm(t("settings.deleteSourceConfirm"));
    if (!confirmed) return;
  }

  const button = qs("#btn-apply-data-migration");
  if (button) {
    button.disabled = true;
    button.classList.add("btn-disabled");
    button.textContent = t("settings.migrating");
  }

  try {
    const result = await apiFetch("/api/projects/data-migration/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_ids: selected, delete_source: deleteSource })
    });
    migrationScan = result;
    renderProjectDataMigration();
    eventBus.emit("reload-projects");
    eventBus.emit("toast", t("settings.migrationCompleted", { copied: result.migrated?.length || 0, deleted: result.deleted?.length || 0 }));
  } catch (err) {
    eventBus.emit("toast", t("settings.migrationFailed", { message: err.message }));
  } finally {
    if (button) button.textContent = t("settings.copySelectedProjects");
    updateMigrationApplyButton();
  }
}

function renderProjectDataMigration() {
  const paths = qs("#project-data-migration-paths");
  if (paths) {
    paths.innerHTML = `
      <div class="path-row"><span>${escapeHtml(t("settings.source"))}</span><code>${escapeHtml(migrationScan?.source_root || t("settings.notScanned"))}</code></div>
      <div class="path-row"><span>${escapeHtml(t("settings.target"))}</span><code>${escapeHtml(migrationScan?.target_root || t("settings.notScanned"))}</code></div>
    `;
  }
  const list = qs("#project-data-migration-list");
  if (!list) return;
  if (!migrationScan) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(t("settings.scanFirst"))}</div>`;
    updateMigrationApplyButton();
    return;
  }
  if (migrationScan.same_root) {
    list.innerHTML = `<div class="empty-state">${escapeHtml(t("settings.sameProjectRoot"))}</div>`;
    updateMigrationApplyButton();
    return;
  }
  const candidates = migrationScan.candidates || [];
  const messages = [
    ...(migrationScan.errors || []).map((msg) => `<div class="status-guard danger"><div class="guard-title">${escapeHtml(t("settings.error"))}</div><ul><li>${escapeHtml(msg)}</li></ul></div>`),
    ...(migrationScan.skipped || []).map((item) => `<div class="status-guard warning"><div class="guard-title">${escapeHtml(t("settings.skipped"))}</div><ul><li>${escapeHtml(item.project_id)}: ${escapeHtml(item.reason || t("settings.skipped"))}</li></ul></div>`),
  ].join("");
  if (!candidates.length) {
    list.innerHTML = `${messages}<div class="empty-state">${escapeHtml(t("settings.noLegacyProjects"))}</div>`;
    updateMigrationApplyButton();
    return;
  }
  list.innerHTML = `${messages}${candidates.map(renderMigrationCandidate).join("")}`;
  qsa("[data-migration-project]").forEach((item) => item.addEventListener("change", updateMigrationApplyButton));
  updateMigrationApplyButton();
}

function renderMigrationCandidate(item) {
  const disabled = item.target_exists ? "disabled" : "";
  const checked = item.target_exists ? "" : "checked";
  return `
    <article class="project-history-card migration-candidate-card">
      <div class="project-history-main">
        <label class="migration-candidate-title">
          <input type="checkbox" data-migration-project value="${escapeHtml(item.project_id)}" ${checked} ${disabled}>
          <div>
            <div class="project-history-title-row">
              <h3>${escapeHtml(item.project_name || item.project_id)}</h3>
              <span class="badge ${item.target_exists ? "badge-warning" : "badge-info"}">${escapeHtml(item.target_exists ? t("settings.targetExists") : t("common.ready"))}</span>
              <span class="badge badge-muted">${escapeHtml(item.task_type || "--")}</span>
            </div>
            <p>${formatBytes(item.size_bytes)} · ${escapeHtml(item.updated_at || item.created_at || "--")}</p>
          </div>
        </label>
      </div>
      <div class="project-file-details">
        <div><span>${escapeHtml(t("settings.source"))}</span><code>${escapeHtml(item.source_path)}</code></div>
        <div><span>${escapeHtml(t("settings.target"))}</span><code>${escapeHtml(item.target_path)}</code></div>
      </div>
    </article>
  `;
}

function updateMigrationApplyButton() {
  const button = qs("#btn-apply-data-migration");
  if (!button) return;
  const count = qsa("[data-migration-project]:checked").length;
  button.disabled = count === 0;
  button.classList.toggle("btn-disabled", count === 0);
  button.textContent = count ? t("settings.copySelectedCount", { count }) : t("settings.copySelectedProjects");
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
