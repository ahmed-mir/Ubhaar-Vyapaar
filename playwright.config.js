const { defineConfig, devices } = require("@playwright/test");

const localPort = process.env.UBHAAR_E2E_PORT || "8010";
const localBaseURL = `http://127.0.0.1:${localPort}`;
const baseURL = process.env.UBHAAR_BASE_URL || localBaseURL;
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
        command: `python manage.py runserver 127.0.0.1:${localPort} --settings=config.settings_e2e --noreload`,
        url: `${localBaseURL}/health/`,
        reuseExistingServer: false,
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
