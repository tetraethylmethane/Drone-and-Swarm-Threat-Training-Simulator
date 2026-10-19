// Records a walkthrough video of the web trainer for the project website (not a test).
// Development stack only, synthetic training data.
import { expect, test } from "@playwright/test";

import { login, newUserPage } from "../specs/helpers";

const OUT = process.env.UX_OUT ?? "recordings";

test("record walkthrough", async ({ browser }) => {
  test.setTimeout(600_000);
  // Set up the assignment off camera.
  const ins = await newUserPage(browser, "instructor");
  await ins.goto("/instructor/assignments/new");
  const scenario = ins.getByRole("combobox", { name: "Scenario" });
  const opt = await scenario.locator("option", { hasText: "Coordinated Swarm Recognition" }).first().getAttribute("value");
  await scenario.selectOption(opt ?? "");
  await ins.getByLabel("Title").fill("Swarm defence drill");
  await ins.getByLabel("Starting level").selectOption("3");
  await ins.getByLabel(/Demo Trainee One/).check();
  await ins.getByRole("button", { name: /^Assign/ }).click();
  await expect(ins.getByText("Swarm defence drill").first()).toBeVisible();

  // The trainee, on camera.
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    recordVideo: { dir: OUT, size: { width: 1600, height: 900 } },
  });
  const tr = await ctx.newPage();
  await login(tr, "trainee1");
  await tr.goto("/trainee");
  await tr.waitForTimeout(2500);
  await tr.locator("tr", { hasText: "Swarm defence drill" }).first().getByRole("link", { name: /Open|Resume/ }).click();
  await tr.waitForTimeout(2500);
  await tr.getByRole("button", { name: /Prepare exercise|Resume exercise/ }).click();
  await expect(tr.getByText(/^(Ready to start|Running|Paused)$/)).toBeVisible({ timeout: 60_000 });
  await tr.waitForTimeout(1500);
  const start = tr.getByRole("button", { name: "Start exercise" });
  if (await start.isVisible()) await start.click();
  await expect(tr.getByLabel(/^Select TRK-\d{3}$/).first()).toBeVisible({ timeout: 120_000 });
  await tr.waitForTimeout(25_000); // let the swarm come in
  await tr.getByRole("button", { name: "Plan view" }).click();
  await tr.waitForTimeout(4000);

  const boxes = tr.getByLabel(/^Select TRK-\d{3}$/);
  const n = Math.min(await boxes.count(), 6);
  for (let i = 0; i < n; i++) {
    await boxes.nth(i).check();
    await tr.waitForTimeout(600);
    await tr.getByLabel("Classification").selectOption({ label: "Coordinated swarm" }).catch(() => {});
    await tr.waitForTimeout(500);
    await tr.getByRole("button", { name: "Submit classification" }).click().catch(() => {});
    await tr.waitForTimeout(700);
    await tr.getByRole("button", { name: /Report to exercise control/ }).click().catch(() => {});
    await tr.waitForTimeout(700);
    await boxes.nth(i).uncheck().catch(() => {});
  }
  await tr.getByRole("button", { name: "3D view" }).click();
  await tr.waitForTimeout(5000);
  await tr.getByRole("button", { name: "Finish exercise" }).click();
  await tr.waitForTimeout(800);
  await tr.getByRole("button", { name: "Finish and score" }).click();
  await expect(tr.getByRole("heading", { name: "Performance breakdown" })).toBeVisible({ timeout: 60_000 });
  await tr.waitForTimeout(3500);
  await tr.mouse.wheel(0, 500);
  await tr.waitForTimeout(3000);
  await tr.mouse.wheel(0, 700);
  await tr.waitForTimeout(3000);
  await tr.mouse.wheel(0, -1200);
  await tr.getByRole("tab", { name: "Track decisions" }).click();
  await tr.waitForTimeout(4000);
  await ctx.close(); // writes the video
});
