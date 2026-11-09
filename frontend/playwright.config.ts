import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke tests against the real backend (recorded answers only, no API key) and the Next.js
 * dev server. Reports and traces go to PW_REPORT_DIR and PW_OUTPUT_DIR when set, so they can
 * live outside the repo. PLAYWRIGHT_CHROMIUM_PATH points at an installed Chromium when the
 * bundled one has not been downloaded.
 */
const chromiumPath = process.env.PLAYWRIGHT_CHROMIUM_PATH;

export default defineConfig({
  testDir: "tests/e2e",
  outputDir: process.env.PW_OUTPUT_DIR ?? "test-results",
  reporter: [["list"], ["html", { outputFolder: process.env.PW_REPORT_DIR ?? "playwright-report", open: "never" }]],
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://localhost:3000",
    trace: "off",
    ...(chromiumPath ? { launchOptions: { executablePath: chromiumPath } } : {}),
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: "uv run uvicorn app.main:app --port 8000",
      cwd: "../backend",
      env: { ANTHROPIC_API_KEY: "" },
      url: "http://localhost:8000/api/users",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
