#!/usr/bin/env node
import process from "node:process";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const PROJECT_ROOT = resolve(SCRIPT_DIR, "..");
const LOCAL_AUDIT_NODE_MODULES = resolve(PROJECT_ROOT, "tools", "i18n-audit", "node_modules");

const args = parseArgs(process.argv.slice(2));
const url = args.url || "http://127.0.0.1:18080/";
const lang = args.lang || "zh-TW";
const failOnIssues = Boolean(args["fail-on-issues"]);
const auditTargets = parseAuditTargets(args.pages || args.nav || "");
const englishPattern = /[A-Za-z]{3,}(?:\s+[A-Za-z]{2,})?/;
const mojibakePattern = /[�]|嚗|銝|撠|蝣|閮|隢||||||/;

let chromium;
try {
  ({ chromium } = await loadPlaywright());
} catch (error) {
  console.error(JSON.stringify({
    ok: false,
    error: "Playwright is required. Install project dev dependencies or set PLAYWRIGHT_NODE_MODULES to a node_modules folder containing Playwright.",
    detail: error.message,
  }, null, 2));
  process.exit(2);
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.addInitScript((nextLang) => {
  localStorage.setItem("vts-language", nextLang);
}, lang);
const page = await context.newPage();
const issues = [];

try {
  await page.goto(url, { waitUntil: "networkidle", timeout: Number(args.timeout || 30000) });
  await page.evaluate((nextLang) => {
    localStorage.setItem("vts-language", nextLang);
    document.documentElement.lang = nextLang;
    window.dispatchEvent(new CustomEvent("language-changed", { detail: { language: nextLang } }));
  }, lang);
  await page.waitForTimeout(Number(args.settle || 600));

  const targets = auditTargets.length ? auditTargets : [{ mode: "", page: "", label: "initial" }];
  let scanned = 0;
  for (const target of targets) {
    await navigateAuditTarget(page, target);
    await page.waitForTimeout(Number(args.settle || 600));
    const snapshot = await collectSnapshot(page);
    scanned += snapshot.length;

    for (const item of snapshot) {
      const text = item.text || "";
      const scopedItem = { ...item, page: target.label };
      if (mojibakePattern.test(text)) {
        issues.push({ ...scopedItem, issue: "mojibake" });
      } else if (lang.toLowerCase().startsWith("zh") && englishPattern.test(text) && !allowedEnglish(text)) {
        issues.push({ ...scopedItem, issue: "english_in_zh_mode" });
      }
    }
  }

  const result = {
    ok: issues.length === 0,
    url,
    lang,
    pages: targets.map((target) => target.label),
    scanned,
    issue_count: issues.length,
    issues: issues.slice(0, Number(args.limit || 200)),
  };
  console.log(JSON.stringify(result, null, 2));
  if (failOnIssues && issues.length) process.exitCode = 1;
} finally {
  await context.close();
  await browser.close();
}

function parseAuditTargets(value) {
  return String(value || "")
    .split(",")
    .map((raw) => raw.trim())
    .filter(Boolean)
    .map((raw) => {
      const [maybeMode, maybePage] = raw.includes(":") ? raw.split(":", 2) : ["", raw];
      const mode = ["cnn", "rnn"].includes(maybeMode) ? maybeMode : "";
      const page = maybePage || maybeMode || "";
      return {
        mode,
        page,
        label: mode ? `${mode}:${page}` : page,
      };
    });
}

async function navigateAuditTarget(page, target) {
  if (target.mode) {
    await clickFirstVisible(page, `[data-training-mode="${target.mode}"]`);
  }
  if (!target.page) return;
  const selectors = target.mode === "rnn"
    ? [`[data-rnn-nav="${target.page}"]`, `[data-page="${target.page}"]`]
    : target.mode === "cnn"
      ? [`[data-cnn-nav="${target.page}"]`, `[data-page="${target.page}"]`]
      : [`[data-page="${target.page}"]`, `[data-mode-nav="${target.page}"]`];
  for (const selector of selectors) {
    if (await clickFirstVisible(page, selector)) {
      return;
    }
  }
}

async function clickFirstVisible(page, selector) {
  const locators = page.locator(selector);
  const count = await locators.count();
  for (let index = 0; index < count; index += 1) {
    const locator = locators.nth(index);
    if (await locator.isVisible()) {
      await locator.click({ timeout: 5000 });
      return true;
    }
  }
  return false;
}

async function collectSnapshot(page) {
  return page.evaluate(() => {
    const isVisible = (element) => {
      const style = window.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
    };
    const visibleText = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const text = (node.nodeValue || "").replace(/\s+/g, " ").trim();
      if (!text || text.length < 2) continue;
      const parent = node.parentElement;
      if (!parent || !isVisible(parent)) continue;
      visibleText.push({
        kind: "visible_text",
        text,
        selector: parent.id ? `#${parent.id}` : parent.tagName.toLowerCase(),
      });
    }
    const attrs = [];
    const attrNames = ["data-tooltip", "placeholder", "title", "aria-label", "alt"];
    document.querySelectorAll("*").forEach((element) => {
      attrNames.forEach((attr) => {
        const value = element.getAttribute(attr);
        if (!value || !value.trim()) return;
        attrs.push({
          kind: attr,
          text: value.replace(/\s+/g, " ").trim(),
          selector: element.id ? `#${element.id}` : element.tagName.toLowerCase(),
        });
      });
    });
    return [...visibleText, ...attrs];
  });
}

function parseArgs(argv) {
  const parsed = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      parsed._.push(arg);
      continue;
    }
    const key = arg.slice(2);
    const next = argv[index + 1];
    if (!next || next.startsWith("--")) {
      parsed[key] = true;
    } else {
      parsed[key] = next;
      index += 1;
    }
  }
  if (!parsed.url && parsed._[0]) parsed.url = parsed._[0];
  if (!parsed.lang && parsed._[1]) parsed.lang = parsed._[1];
  return parsed;
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (initialError) {
    const require = createRequire(import.meta.url);
    const failures = [initialError.message];
    const candidates = [
      process.env.PLAYWRIGHT_NODE_MODULES,
      process.env.PLAYWRIGHT_NODE_MODULES ? `${process.env.PLAYWRIGHT_NODE_MODULES}/..` : "",
      LOCAL_AUDIT_NODE_MODULES,
      "C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node",
      "C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules",
    ].filter(Boolean);
    for (const candidate of candidates) {
      try {
        const resolved = require.resolve("playwright", { paths: [candidate] });
        return require(resolved);
      } catch (error) {
        failures.push(`${candidate}: ${error.message}`);
        try {
          return require(`${candidate.replace(/\\/g, "/")}/playwright`);
        } catch (directError) {
          failures.push(`${candidate}/playwright: ${directError.message}`);
          // Continue to next candidate.
        }
      }
    }
    throw new Error(failures.join(" | "));
  }
}

function allowedEnglish(text) {
  const trimmed = String(text || "").trim();
  if (trimmed.includes("Vision Training Studio")) return true;
  if (trimmed.includes("LabelMe")) return true;
  if (/^\d+\s+projects?$/i.test(trimmed)) return true;
  if (/\bUpdated\s+\d{4}-\d{2}-\d{2}/i.test(trimmed)) return true;
  if (/^[a-z0-9][a-z0-9_.-]*[_0-9.-][a-z0-9_.-]*$/i.test(trimmed)) return true;
  if (/^[A-Za-z]:[\\/]/.test(trimmed) || /[A-Za-z]:[\\/]/.test(trimmed) || trimmed.includes(":/")) return true;
  if (/run_YYYYMMDD_HHMMSS/i.test(trimmed)) return true;
  if (/\b(run|mAP|IoU|bbox|COCO|mask|ZIP|RAG|RNN|CNN|CSV|XML|JSON|HTML|CSS|JS|ONNX|TensorRT|PyTorch|Ultralytics|Python|Markdown|schema|learning rate|mosaic augmentation|Stratified|Group|epoch|checkpoint|VRAM|CUDA|CPU|GPU|Auto|timestep|timestamp|Date Time|time steps|sequence_length|stride|horizon|class_[a-z]|class_names|sequence_id|machine_id|batch_id|RoadSeg|builtin|ultralytics_yolo|Instance Segmentation|my_vision_project|defect|scratch|stain)\b/i.test(trimmed)) {
    return true;
  }
  if (/\b(MP4|AVI|MKV|MOV|WMV|FLV|WEBM|P0|best\.pt|last\.pt|\.pt|\.onnx|annotations\/|training\/runs|train\/loss|val\/loss)\b/i.test(trimmed)) return true;
  if (/\b(Loss|Accuracy|Macro-F1|Precision|Recall|MAE|RMSE|mAP50|Classification|Regression|Sequence|Trainable|Optional|Epochs|Batch Size|Dropout|Schema|Train|Val|Test|Box|Note|Head|Total|Runs|Labels|Features|Primary|Export Model|Export PT|Report|Semantic Mask)\b/.test(trimmed)) return true;
  if (/\b(normal|abnormal|validation loss|task head|Package registry|adapter|package contract|target|label sequence|residual|transition stability|sequence_regression|sequence_classification|semantic_segmentation|classification|regression|road|T \(degC\)|target_reg|Features \/ X)\b/i.test(trimmed)) return true;
  if (/sequences\/features\.csv/i.test(trimmed)) return true;
  if (/^[A-Za-z]\s*\([^)]+\)$/.test(trimmed)) return true;
  if (/^(RAG|RNN|CNN|GPU|RAM|CSV|ZIP|ONNX|TensorRT|XGBoost|LSTM|GRU|BiLSTM|MAE|RMSE|JSON|HTML|CSS|JS|LabelMe|YOLO)$/i.test(trimmed)) {
    return true;
  }
  if (/^(RAG|RNN|CNN|GPU|RAM|CSV|ZIP|ONNX|TensorRT|XGBoost|LSTM|GRU|BiLSTM|MAE|RMSE|JSON|HTML|CSS|JS|LabelMe|YOLO)\b/i.test(trimmed)) {
    return true;
  }
  if (/^[A-Z0-9_\-./:]+$/.test(trimmed)) return true;
  if (/^[\w.-]+\.(json|csv|pt|onnx|zip|yaml|yml|md)$/i.test(trimmed)) return true;
  return false;
}
