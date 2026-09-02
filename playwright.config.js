import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "tests/e2e",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  use: {
    baseURL: "http://127.0.0.1:18117",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "python -m uvicorn app:app --host 127.0.0.1 --port 18117",
    url: "http://127.0.0.1:18117/api/health",
    reuseExistingServer: true,
    timeout: 120_000,
    env: { VTS_ENV: "test", LOCAL_TRUSTED_MODE: "true" },
  },
});
