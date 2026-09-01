import { defineConfig } from "@playwright/test";

const authorizedUtmTarget = process.env.AI_UTM_AUTHORIZED === "1" && Boolean(process.env.AI_UTM_BASE_URL);
const chromeExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const requestedSpecs = process.argv.filter((argument) => argument.includes(".spec."));
const requestedUtmProject = process.argv.some((argument, index, argumentsList) => argument === "--project=utm" || (argument === "--project" && argumentsList[index + 1] === "utm"));
const requestedChromiumProject = process.argv.some((argument, index, argumentsList) => argument === "--project=chromium" || (argument === "--project" && argumentsList[index + 1] === "chromium"));
const utmOnlyInvocation =
  (requestedSpecs.some((argument) => argument.includes("utm.spec.")) && !requestedSpecs.some((argument) => argument.includes("standalone.spec."))) ||
  (requestedUtmProject && !requestedChromiumProject);
const standaloneWebServers = [
  {
    command: "../.venv/bin/python3 e2e/standalone_server.py --database /private/tmp/librenms-ai-assistant-playwright.sqlite3",
    url: "http://127.0.0.1:8765/docs",
    reuseExistingServer: false,
    timeout: 30_000,
  },
  {
    command: "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: false,
    timeout: 30_000,
  },
];

export default defineConfig({
  testDir: "./e2e",
  outputDir: "../e2e-artifacts/playwright/test-results",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  reporter: [["list"], ["html", { outputFolder: "../e2e-artifacts/playwright/report", open: "never" }]],
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    headless: true,
    launchOptions: { executablePath: chromeExecutable },
  },
  projects: [
    { name: "chromium", testMatch: /standalone\.spec\.js/, use: { baseURL: "http://127.0.0.1:5173" } },
    {
      name: "utm",
      testMatch: /utm\.spec\.js/,
      use: authorizedUtmTarget ? { baseURL: process.env.AI_UTM_BASE_URL } : {},
    },
  ],
  // A UTM-only invocation has no fixture server and no fallback URL. It cannot
  // touch a target unless the operator supplies the explicit authorization.
  webServer: utmOnlyInvocation ? undefined : standaloneWebServers,
});
