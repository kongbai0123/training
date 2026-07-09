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

  const snapshot = await page.evaluate(() => {
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

  for (const item of snapshot) {
    const text = item.text || "";
    if (mojibakePattern.test(text)) {
      issues.push({ ...item, issue: "mojibake" });
    } else if (lang.toLowerCase().startsWith("zh") && englishPattern.test(text) && !allowedEnglish(text)) {
      issues.push({ ...item, issue: "english_in_zh_mode" });
    }
  }

  const result = {
    ok: issues.length === 0,
    url,
    lang,
    scanned: snapshot.length,
    issue_count: issues.length,
    issues: issues.slice(0, Number(args.limit || 200)),
  };
  console.log(JSON.stringify(result, null, 2));
  if (failOnIssues && issues.length) process.exitCode = 1;
} finally {
  await context.close();
  await browser.close();
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
  if (/^[A-Za-z]:[\\/]/.test(trimmed) || /[A-Za-z]:[\\/]/.test(trimmed) || trimmed.includes(":/")) return true;
  if (/run_YYYYMMDD_HHMMSS/i.test(trimmed)) return true;
  if (/\b(run|mAP|IoU|bbox|COCO|mask|ZIP|RNN|CNN|CSV|learning rate|mosaic augmentation|Stratified|Group|epoch|checkpoint|VRAM|CUDA|CPU|GPU|Auto|timestep|timestamp|Date Time|time steps|horizon|class_[a-z]|sequence_id|machine_id|batch_id|RoadSeg|builtin|ultralytics_yolo|Instance Segmentation|my_vision_project|defect|scratch|stain)\b/i.test(trimmed)) {
    return true;
  }
  if (/sequences\/features\.csv/i.test(trimmed)) return true;
  if (/^(RNN|CNN|GPU|RAM|CSV|ZIP|ONNX|TensorRT|XGBoost|LSTM|GRU|BiLSTM|MAE|RMSE|JSON|LabelMe|YOLO)$/i.test(trimmed)) {
    return true;
  }
  if (/^(RNN|CNN|GPU|RAM|CSV|ZIP|ONNX|TensorRT|XGBoost|LSTM|GRU|BiLSTM|MAE|RMSE|JSON|LabelMe|YOLO)\b/i.test(trimmed)) {
    return true;
  }
  if (/^[A-Z0-9_\-./:]+$/.test(trimmed)) return true;
  if (/^[\w.-]+\.(json|csv|pt|onnx|zip|yaml|yml|md)$/i.test(trimmed)) return true;
  return false;
}
