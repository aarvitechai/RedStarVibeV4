import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running stack (Blueprint 27.2: Playwright at 360, 768 and 1280 px).
 *   E2E_BASE_URL=http://localhost:8090 npm test
 */
export default defineConfig({
  testDir: "./tests",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8080",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "mobile-360", use: { ...devices["Pixel 7"], viewport: { width: 360, height: 780 } } },
    { name: "tablet-768", use: { viewport: { width: 768, height: 1024 } } },
    { name: "desktop-1280", use: { viewport: { width: 1280, height: 800 } } },
  ],
});
