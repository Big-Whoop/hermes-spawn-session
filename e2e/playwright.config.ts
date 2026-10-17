import { defineConfig } from '@playwright/test'

// Specs run serially: parallel Electron + backend stacks are flaky upstream
// (research REPORT.md, lane 3), and all specs share one backend.
//
// Projects:
// - backend: REST checks against an isolated `hermes serve --port 0` that the
//   global setup starts, or an external one via HERMES_DESKTOP_REMOTE_URL/_TOKEN.
// - desktop: Playwright `_electron` against a Hermes Desktop source build
//   (HERMES_DESKTOP_ROOT). Skipped when HERMES_DESKTOP_ROOT is unset.
const artifacts = process.env.E2E_ARTIFACTS_DIR || 'test-results'

export default defineConfig({
  testDir: './specs',
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  outputDir: `${artifacts}/output`,
  // Global setup returns its own teardown (keeps the mock server handle).
  globalSetup: './support/global-setup.ts',
  reporter: [
    ['list'],
    ['junit', { outputFile: `${artifacts}/junit.xml` }],
    ['html', { outputFolder: `${artifacts}/html`, open: 'never' }]
  ],
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure'
  },
  projects: [
    { name: 'backend', testMatch: /backend\..*\.spec\.ts$/ },
    { name: 'desktop', testMatch: /desktop\..*\.spec\.ts$/, dependencies: ['backend'] }
  ]
})
