import { applyZhFallbackTranslations, configureI18nFallback, restoreFallbackTranslations } from "../i18n_fallback.js";
import { zhTW } from "./i18n/zh-TW.js";
import { en } from "./i18n/en.js";

let zhFallbackObserver = null;
let zhFallbackScheduled = false;
let activeLanguage = "zh-TW";

function isSafeTranslationText(value) {
  if (value == null) return false;
  const text = String(value);
  if (!text.trim()) return false;
  return !/[\uFFFD\uE000-\uF8FF]/.test(text);
}

function safeCatalogValue(dict, key, fallback) {
  const value = dict?.[key];
  return isSafeTranslationText(value) ? value : fallback;
}

function scheduleZhFallbackTranslations() {
  if (activeLanguage !== "zh-TW") return;
  if (zhFallbackScheduled) return;
  zhFallbackScheduled = true;
  requestAnimationFrame(() => {
    zhFallbackScheduled = false;
    applyZhFallbackTranslations(document.body);
  });
}

function ensureZhFallbackObserver() {
  if (zhFallbackObserver || typeof MutationObserver === "undefined") return;
  zhFallbackObserver = new MutationObserver((mutations) => {
    if (activeLanguage !== "zh-TW") return;
    if (!mutations.some((mutation) => mutation.addedNodes?.length || mutation.type === "attributes")) return;
    scheduleZhFallbackTranslations();
  });
  zhFallbackObserver.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["placeholder", "title", "aria-label", "data-tooltip", "alt"]
  });
}


export const i18n = {
  "zh-TW": zhTW,
  en,
};

export function translate(key, language = "zh-TW", params = {}) {
  const lang = language === "en" ? "en" : "zh-TW";
  const fallback = i18n.en?.[key] ?? key;
  const template = safeCatalogValue(i18n[lang], key, fallback);
  return String(template).replace(/\{(\w+)\}/g, (_, name) => params[name] ?? "");
}


export function applyLanguageToDocument({ language, theme, translate }) {
  const nextLanguage = language === "en" ? "en" : "zh-TW";
  activeLanguage = nextLanguage;

  const languageSelect = document.querySelector("#settings-language");
  if (languageSelect) languageSelect.value = nextLanguage;

  const dict = i18n[nextLanguage];
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.dataset.i18n;
    const value = safeCatalogValue(dict, key, i18n.en?.[key]);
    if (!value) return;
    el.textContent = value;
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    const key = el.dataset.i18nPlaceholder;
    const value = safeCatalogValue(dict, key, i18n.en?.[key]);
    if (!value) return;
    el.setAttribute("placeholder", value);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    const key = el.dataset.i18nTitle;
    const value = safeCatalogValue(dict, key, i18n.en?.[key]);
    if (!value) return;
    el.setAttribute("title", value);
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => {
    const key = el.dataset.i18nAriaLabel;
    const value = safeCatalogValue(dict, key, i18n.en?.[key]);
    if (!value) return;
    el.setAttribute("aria-label", value);
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => {
    const key = el.dataset.i18nAlt;
    const value = safeCatalogValue(dict, key, i18n.en?.[key]);
    if (!value) return;
    el.setAttribute("alt", value);
  });
  document.querySelectorAll("[data-i18n-tooltip]").forEach((el) => {
    const key = el.dataset.i18nTooltip;
    const value = safeCatalogValue(dict, key, i18n.en?.[key]);
    if (!value) return;
    el.dataset.tooltip = value;
  });

  const themeLabel = document.querySelector("[data-i18n='themeToggle']");
  if (themeLabel) {
    themeLabel.textContent = theme === "dark" ? dict.themeToggle : dict.themeToggleDark;
  }

  document.documentElement.lang = nextLanguage;
  configureI18nFallback(translate);
  if (nextLanguage === "zh-TW") {
    applyZhFallbackTranslations(document.body);
    ensureZhFallbackObserver();
  } else {
    restoreFallbackTranslations(document.body);
  }
}
