import { defineConfig, devices } from "@playwright/test";

const port = process.env.E2E_PORT || "4173";
const baseURL = process.env.E2E_BASE_URL || `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never", outputFolder: "playwright-report" }], ["list"]]
    : [["list"]],
  timeout: 60_000,
  expect: { timeout: 15_000 },
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    locale: "en-US",
  },
  outputDir: "test-results",
  webServer: {
    command: "node scripts/preview-e2e.mjs",
    url: `${baseURL}/zh-CN/`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
