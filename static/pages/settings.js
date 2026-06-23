import { eventBus } from "../event_bus.js";
import { appState, applyTheme, applyLanguage } from "../state.js";
import { qs } from "../utils.js";

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
}

export function renderSettingsPage() {
  const langSelect = qs("#settings-language");
  if (langSelect) langSelect.value = appState.settings.language;

  const themeSelect = qs("#settings-theme");
  if (themeSelect) themeSelect.value = appState.settings.theme;
}
