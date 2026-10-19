import { defineConfig, devices } from "@playwright/test";

// Usability walkthrough (docs/testing/instructor-usability-protocol.md §6): not part of CI.
export default defineConfig({
  testDir: ".",
  timeout: 300_000,
  workers: 1,
  reporter: [["list"]],
  expect: { timeout: 10_000 },
  outputDir: process.env.UX_OUT ? `${process.env.UX_OUT}/results` : "ux-results",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:4173",
    ...devices["Desktop Chrome"],
    viewport: { width: 1920, height: 1080 },
    actionTimeout: 10_000,
  },
});
