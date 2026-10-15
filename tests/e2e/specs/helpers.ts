import { createHmac } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, type Browser, type Page } from "@playwright/test";

export const PASSWORD = process.env.E2E_PASSWORD ?? "Training-Pass-2026!";

// --- TOTP (RFC 6238, SHA-1, 6 digits, 30 s), used to drive real MFA through the UI -------------

function base32Decode(s: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0;
  let value = 0;
  const out: number[] = [];
  for (const ch of s.replace(/=+$/, "").toUpperCase()) {
    value = (value << 5) | alphabet.indexOf(ch);
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(out);
}

export function totp(secret: string, step: number): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(step));
  const mac = createHmac("sha1", base32Decode(secret)).update(counter).digest();
  const offset = mac[mac.length - 1] & 0x0f;
  const code = (mac.readUInt32BE(offset) & 0x7fffffff) % 1_000_000;
  return code.toString().padStart(6, "0");
}

// The authenticator secret of each account the tests enrol, kept outside the repository. If it is
// lost while the account still has MFA on, reset it: drikr-api reset-mfa --username <name>.
const stateFile = (username: string) =>
  join(tmpdir(), `drikr-e2e-mfa-${username}.json`);
type MfaState = { secret: string; lastStep: number };

function readState(username: string): MfaState | null {
  const f = stateFile(username);
  return existsSync(f)
    ? (JSON.parse(readFileSync(f, "utf8")) as MfaState)
    : null;
}

function writeState(username: string, state: MfaState): void {
  writeFileSync(stateFile(username), JSON.stringify(state));
}

/** A code for a time step not used before: the server rejects a replayed step. */
async function freshCode(username: string): Promise<string> {
  const state = readState(username);
  if (!state)
    throw new Error(
      `${username} has MFA on but no stored secret; run drikr-api reset-mfa --username ${username}`,
    );
  let step = Math.floor(Date.now() / 30_000);
  while (step <= state.lastStep) {
    await new Promise((r) => setTimeout(r, 1000));
    step = Math.floor(Date.now() / 30_000);
  }
  writeState(username, { ...state, lastStep: step });
  return totp(state.secret, step);
}

/** Enrol the signed-in user from the account page (used when their role requires MFA). */
export async function enrolMfa(
  page: Page,
  username: string,
  password = PASSWORD,
): Promise<string> {
  const panel = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Multi-factor authentication" }),
  });
  await panel.getByRole("button", { name: "Set up authenticator" }).click();
  await panel.getByLabel("Current password").fill(password);
  await panel.getByRole("button", { name: "Continue" }).click();
  await expect(panel.getByRole("img", { name: /QR code/ })).toBeVisible();
  const secret = (await panel
    .getByText(/^[A-Z2-7]{32}$/)
    .textContent())!.trim();
  const step = Math.floor(Date.now() / 30_000);
  writeState(username, { secret, lastStep: step });
  await panel
    .getByLabel("Code from your authenticator app")
    .fill(totp(secret, step));
  await panel.getByRole("button", { name: "Turn on" }).click();
  await expect(
    panel.getByRole("list", { name: "Recovery codes" }),
  ).toBeVisible();
  await panel.getByRole("button", { name: "I have saved these codes" }).click();
  await expect(panel.getByText("On", { exact: true })).toBeVisible();
  return secret;
}

export async function login(
  page: Page,
  username: string,
  password = PASSWORD,
  { showGuide = false }: { showGuide?: boolean } = {},
): Promise<void> {
  // The first-visit "How to play" welcome would cover other tests; guide.spec.ts tests it.
  if (!showGuide)
    await page.addInitScript(() => {
      try {
        window.localStorage.setItem("drikr.guide.seen.v1", "1");
      } catch {
        /* storage unavailable */
      }
    });
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  const codeStep = page.getByRole("heading", { name: "Verification code" });
  await expect(
    codeStep.or(
      page.getByRole("heading", { level: 1 }).filter({ hasNotText: "Sign in" }),
    ),
  ).toBeVisible();
  if (await codeStep.isVisible()) {
    await page.getByLabel("Code").fill(await freshCode(username));
    await page.getByRole("button", { name: "Verify and sign in" }).click();
  }
  await expect(page).not.toHaveURL(/\/login$/);
  if (
    await page.getByText("Multi-factor authentication required").isVisible()
  ) {
    await enrolMfa(page, username, password);
    await page.goto("/");
  }
}

export async function newUserPage(
  browser: Browser,
  username: string,
): Promise<Page> {
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  await login(page, username);
  return page;
}

export function unique(prefix: string): string {
  return `${prefix} ${new Date()
    .toISOString()
    .replace(/[-:.TZ]/g, "")
    .slice(0, 14)}`;
}
