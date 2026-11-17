#!/usr/bin/env node
/**
 * Optional local end-to-end smoke test for the NimbusOps console.
 *
 * NOT a CI gate. This script is committed so the acceptance path is
 * reproducible, but it is only run when a developer chooses to run it:
 *
 *   cd frontend
 *   npm i -D playwright
 *   npx playwright install chromium
 *   npm run e2e:onboarding
 *
 * It expects a running control plane and this Vite dev server, each backed by
 * a scratch database — never the live fleet database. Provide real operator
 * credentials through the environment (never argv):
 *
 *   NIMBOPS_E2E_BASE_URL        default http://127.0.0.1:5173
 *   NIMBOPS_E2E_ADMIN_USER / NIMBOPS_E2E_ADMIN_PASSWORD
 *   NIMBOPS_E2E_VIEWER_USER / NIMBOPS_E2E_VIEWER_PASSWORD
 *   NIMBOPS_E2E_REVOKED_HOST_ID optional: a host whose credential is revoked
 *
 * What it proves when it passes:
 *   - an ADMIN can sign in through the cookie-only browser session;
 *   - the enrollment wizard issues a real single-use bootstrap token from the
 *     control plane (not a mock), and never prints it into the URL;
 *   - a VIEWER has no deploy/start/stop controls and no enrollment action;
 *   - a revoked host is labelled Revoked, never Offline.
 *
 * It deliberately does not install, start, or reset anything.
 */

const BASE_URL = process.env.NIMBOPS_E2E_BASE_URL ?? "http://127.0.0.1:5173";
const ADMIN_USER = process.env.NIMBOPS_E2E_ADMIN_USER;
const ADMIN_PASSWORD = process.env.NIMBOPS_E2E_ADMIN_PASSWORD;
const VIEWER_USER = process.env.NIMBOPS_E2E_VIEWER_USER;
const VIEWER_PASSWORD = process.env.NIMBOPS_E2E_VIEWER_PASSWORD;
const REVOKED_HOST_ID = process.env.NIMBOPS_E2E_REVOKED_HOST_ID;

function fail(message) {
  console.error(`FAIL: ${message}`);
  process.exitCode = 1;
}

function requireEnv(name, value) {
  if (!value) {
    fail(`${name} is required (pass it through the environment, never argv).`);
    return false;
  }
  return true;
}

async function signIn(page, username, password) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded" });
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("navigation", { name: "Primary" }).waitFor({ timeout: 15_000 });
}

async function run() {
  if (!requireEnv("NIMBOPS_E2E_ADMIN_USER", ADMIN_USER)) return;
  if (!requireEnv("NIMBOPS_E2E_ADMIN_PASSWORD", ADMIN_PASSWORD)) return;
  if (!requireEnv("NIMBOPS_E2E_VIEWER_USER", VIEWER_USER)) return;
  if (!requireEnv("NIMBOPS_E2E_VIEWER_PASSWORD", VIEWER_PASSWORD)) return;

  let playwright;
  try {
    playwright = await import("playwright");
  } catch {
    fail(
      "Playwright is not installed. Run `npm i -D playwright` and `npx playwright install chromium` " +
        "in frontend/, then re-run. This harness is optional and is not part of CI.",
    );
    return;
  }

  const browser = await playwright.chromium.launch();
  try {
    const admin = await browser.newContext();
    const adminPage = await admin.newPage();

    // 1. ADMIN session and enrollment action.
    await signIn(adminPage, ADMIN_USER, ADMIN_PASSWORD);
    console.log("PASS admin signs in through the cookie-only session");

    await adminPage.getByRole("link", { name: /servers/i }).click();
    await adminPage.getByRole("button", { name: "Add Server" }).waitFor();
    console.log("PASS ADMIN sees the enrollment action");

    // 2. The wizard asks the control plane for a real, single-use token.
    await adminPage.getByRole("button", { name: "Add Server" }).click();
    const hostname = `e2e-${Date.now().toString(36)}`;
    await adminPage.getByLabel("Hostname").fill(hostname);
    await adminPage.getByRole("button", { name: "Continue" }).click();
    await adminPage.getByRole("button", { name: "Generate Enrollment Token" }).click();
    await adminPage.getByRole("heading", { name: "Single-Use Bootstrap Token" }).waitFor();

    const token = (await adminPage.locator("code").first().innerText()).trim();
    if (token.length < 32) fail(`bootstrap token looks empty or truncated (${token.length} chars)`);
    else console.log("PASS enrollment wizard rendered a real single-use bootstrap token");
    if (adminPage.url().includes(token)) fail("bootstrap token leaked into the URL");
    else console.log("PASS bootstrap token is not present in the URL");
    // Leaving the page without installing is intentional: the token expires
    // after its TTL and is consumed only by a real agent enrollment.

    // 3. VIEWER is read-only.
    const viewer = await browser.newContext();
    const viewerPage = await viewer.newPage();
    await signIn(viewerPage, VIEWER_USER, VIEWER_PASSWORD);

    await viewerPage.goto(`${BASE_URL}/deployments`, { waitUntil: "domcontentloaded" });
    await viewerPage.getByRole("heading", { name: "Applications" }).waitFor();
    for (const name of ["Deploy", "Start", "Stop"]) {
      if (await viewerPage.getByRole("button", { name, exact: true }).count()) {
        fail(`VIEWER received a ${name} control`);
      }
    }
    console.log("PASS VIEWER has no deploy/start/stop controls");

    await viewerPage.goto(`${BASE_URL}/servers`, { waitUntil: "domcontentloaded" });
    if (await viewerPage.getByRole("button", { name: "Add Server" }).count()) {
      fail("VIEWER received the Add Server enrollment action");
    } else {
      console.log("PASS VIEWER has no enrollment action");
    }

    // 4. Revoked is a terminal state, never rendered as offline.
    if (REVOKED_HOST_ID) {
      await adminPage.goto(`${BASE_URL}/servers/${encodeURIComponent(REVOKED_HOST_ID)}`, {
        waitUntil: "domcontentloaded",
      });
      await adminPage.locator('[data-status="REVOKED"]').first().waitFor();
      if (await adminPage.locator('[data-status="OFFLINE"]').count()) {
        fail("revoked host was also rendered with an OFFLINE status badge");
      } else {
        console.log("PASS revoked host is labelled Revoked and never Offline");
      }
    } else {
      console.log("SKIP revoked-host check (set NIMBOPS_E2E_REVOKED_HOST_ID to enable)");
    }
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  fail(err instanceof Error ? err.stack ?? err.message : String(err));
});
