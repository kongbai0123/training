// Vision Training Studio - Front-end Entry Module
import { bootstrapApp } from "./core/bootstrap.js?v=20260709-review-first-auto-label";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    bootstrapApp().catch((err) => console.error("Application bootstrap failed:", err));
  }, { once: true });
} else {
  bootstrapApp().catch((err) => console.error("Application bootstrap failed:", err));
}
