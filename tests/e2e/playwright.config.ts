import { tmpdir } from "node:os";
import { join } from "node:path";

import { defineConfig, devices } from "@playwright/test";

/**
 * Runs against an already-started stack (see docs/testing/test-strategy.md):
 *   - API on 127.0.0.1:8000 with the development database seeded via
 *     `drikr-api seed-demo --with-demo-users` (DRIKR_DEMO_PASSWORD must match E2E_PASSWORD)
 *   - web app served on 127.0.0.1:4173 (`npm run build && npx vite preview`) or via docker compose
 * Override the target with E2E_BASE_URL.
 */
export default defineConfig({
  testDir: "./specs",
  // Keep traces and screenshots out of synced folders (OneDrive locking corrupted a trace zip once).
  outputDir: process.env.E2E_OUTPUT_DIR ?? join(tmpdir(), "drikr-e2e-results"),
  timeout: 120_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
