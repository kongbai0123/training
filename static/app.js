// Vision Training Studio - Front-end Entry Module
// Compatibility marker: import { bootstrapApp } from "./core/bootstrap.js?v=20260902-unified-evaluation";
import { bootstrapApp } from "./core/bootstrap.js?v=20260902-commercial-pilot2";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    bootstrapApp().catch((err) => console.error("Application bootstrap failed:", err));
  }, { once: true });
} else {
  bootstrapApp().catch((err) => console.error("Application bootstrap failed:", err));
}
