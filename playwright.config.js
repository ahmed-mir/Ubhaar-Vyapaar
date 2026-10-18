const { defineConfig, devices } = require("@playwright/test");

const baseURL = process.env.UBHAAR_BASE_URL || "http://127.0.0.1:8000";
const useLocalServer = !process.env.UBHAAR_BASE_URL;

module.exports = defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: {
    timeout: 15_000
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["json", { outputFile: "test-results/e2e-results.json" }]
  ],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    actionTimeout: 30_000,
    navigationTimeout: 30_000
  },
  webServer: useLocalServer
    ? {
        command: "python manage.py runserver 127.0.0.1:8000",
        url: "http://127.0.0.1:8000",
        reuseExistingServer: true,
        timeout: 120_000
      }
    : undefined,
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    }
  ]
});
