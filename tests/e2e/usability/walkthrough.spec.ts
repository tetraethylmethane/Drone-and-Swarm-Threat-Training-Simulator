// Scripted walkthrough of the instructor usability tasks T1–T10
// (docs/testing/instructor-usability-protocol.md §4). NOT user data: a script follows the visible
// labels the way a careful newcomer would, so it shows whether each task is possible through the
// interface and how many steps it takes, not whether instructors understand it. Not part of CI.
//
//   cd tests/e2e && UX_OUT=<dir> npx playwright test --config usability/usability.config.ts usability/walkthrough.spec.ts
import { writeFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { newUserPage } from "../specs/helpers";

const OUT = process.env.UX_OUT ?? "ux-shots";
type Row = { task: string; ok: boolean; steps: number; seconds: number; note: string };
const rows: Row[] = [];

async function task(page: Page, id: string, fn: (step: () => void) => Promise<string | void>) {
  let steps = 0;
  const t0 = Date.now();
  let ok = true;
  let note = "";
  try {
    note = (await fn(() => steps++)) ?? "";
  } catch (e) {
    ok = false;
    note = String(e).split("\n")[0].slice(0, 300);
  }
  await page.screenshot({ path: `${OUT}/${id}.png`, fullPage: true });
  rows.push({ task: id, ok, steps, seconds: Math.round((Date.now() - t0) / 100) / 10, note });
}

test("instructor tasks T1–T10", async ({ browser }) => {
  test.setTimeout(600_000);
  const t1 = Date.now();
  const page = await newUserPage(browser, "instructor"); // T1: sign in through the login form
  rows.push({ task: "T1", ok: true, steps: 3, seconds: Math.round((Date.now() - t1) / 100) / 10, note: "" });
  const nav = (name: string) => page.getByRole("navigation").getByRole("link", { name, exact: true });

  await task(page, "T2", async (step) => {
    await nav("Scenarios").click(); step();
    await page.locator("tr", { hasText: "Perimeter Awareness Basics" }).getByRole("link", { name: "Open" }).click(); step();
    await page.getByLabel(/^Level$|Difficulty level/).first().selectOption("3"); step();
    await page.getByRole("button", { name: /Run preview/ }).click(); step();
    await expect(page.getByText(/level 3/i).first()).toBeVisible();
  });

  await task(page, "T3", async (step) => {
    await nav("Scenarios").click(); step();
    await page.locator("tr", { hasText: "Night Loiter Assessment" }).getByRole("link", { name: "Open" }).click(); step();
    await page.getByRole("button", { name: "Edit as new version" }).click(); step();
    await page.getByLabel("Weather").selectOption("fog"); step();
    const vis = page.getByLabel("Visibility (km)");
    if (await page.getByText(/Fog requires visibility/).isVisible()) {
      await vis.fill("1"); step();
    }
    await page.getByRole("button", { name: /Save as version/ }).click(); step();
    await expect(page.getByText(/version \d+ ·/).first()).toBeVisible();
  });

  await task(page, "T4", async (step) => {
    await nav("Assignments").click(); step();
    await page.getByRole("link", { name: /New assignment|Create an assignment/ }).first().click(); step();
    const scenario = page.getByRole("combobox", { name: "Scenario" });
    const opt = await scenario.locator("option", { hasText: "Perimeter Awareness Basics" }).first().getAttribute("value");
    await scenario.selectOption(opt ?? ""); step();
    await page.getByLabel("Title").fill("Usability walkthrough T4"); step();
    await page.getByLabel("Maximum attempts").fill("2"); step();
    const due = new Date(Date.now() + 7 * 864e5).toISOString().slice(0, 10);
    await page.getByLabel(/Due date/).fill(due); step();
    await page.getByLabel("Mode").selectOption({ label: "Adaptive" }); step();
    await page.getByLabel("Starting level").selectOption("1"); step();
    await page.getByLabel("Minimum", { exact: true }).selectOption("1"); step();
    await page.getByLabel("Maximum", { exact: true }).selectOption("3"); step();
    await page.getByLabel(/Demo Trainee One/).check(); step();
    await page.getByLabel(/Demo Trainee Two/).check(); step();
    await page.getByRole("button", { name: /^Assign/ }).click(); step();
    await expect(page.getByText("Usability walkthrough T4").first()).toBeVisible();
  });

  let lowest = "";
  await task(page, "T5", async (step) => {
    await nav("Sessions and reviews").click(); step();
    await page.getByLabel("Sort").selectOption({ index: 0 });
    const options = await page.getByLabel("Sort").locator("option").allTextContents();
    const low = options.find((o) => /lowest|score.*asc|ascending/i.test(o)) ?? "";
    if (!low) throw new Error(`no 'lowest score' sort among: ${options.join(" | ")}`);
    await page.getByLabel("Sort").selectOption({ label: low }); step();
    const first = page.locator("tbody tr").first();
    lowest = (await first.locator("td").first().textContent()) ?? "";
    return `sorted by "${low}"; lowest: ${lowest}. No date filter: "last week" needs reading the Created column`;
  });

  await task(page, "T6", async (step) => {
    await page.locator("tbody tr").first().getByRole("link", { name: "Review" }).click(); step();
    await page.getByRole("tab", { name: "Track decisions" }).click(); step();
    await expect(page.getByRole("table").first()).toBeVisible();
    const incorrect = page.locator("tr", { hasText: /Incorrect|incorrect|Not classified|✗/ }).first();
    if (!(await incorrect.count())) return "no track marked incorrect in this session";
    return `first incorrect row: ${(await incorrect.innerText()).replace(/\s+/g, " ").slice(0, 160)}`;
  });

  await task(page, "T7", async (step) => {
    await page.getByRole("tab", { name: "Export and verification" }).click(); step();
    await page.getByRole("button", { name: "Verify reproducibility" }).click(); step();
    await page.waitForTimeout(3000);
    return (await page.locator("main").innerText()).replace(/\s+/g, " ").match(/(Reproducib|reproducib|Verified|verified)[^.]{0,160}\./g)?.slice(0, 3).join(" | ") ?? "no outcome text found";
  });

  await task(page, "T8", async (step) => {
    await page.getByRole("tab", { name: "Instructor review" }).click(); step();
    await page.getByRole("textbox", { name: "Strengths" }).fill("Classified the swarm early."); step();
    await page.getByRole("textbox", { name: "Areas to improve" }).fill("Request sensor confirmation before clearing."); step();
    await page.getByRole("textbox", { name: "Private notes" }).fill("Private: discuss in debrief."); step();
    await page.getByLabel(/Share strengths/).check(); step();
    await page.getByRole("button", { name: "Save review" }).click(); step();
    await expect(page.getByText(/saved|Saved/).first()).toBeVisible();
  });

  await task(page, "T10", async (step) => {
    await page.getByRole("tab", { name: "Export and verification" }).click(); step();
    const dl = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download PDF report" }).click(); step();
    const f = await dl;
    return `downloaded ${f.suggestedFilename()}`;
  });

  await task(page, "T9", async (step) => {
    await nav("Assignments").click(); step();
    await page.getByRole("link", { name: "Difficulty" }).first().click(); step();
    const why = await page.locator("main").innerText();
    await page.getByLabel("Reason for the change").fill("Consistently above target in the last two attempts."); step();
    const up = page.getByRole("button", { name: /up|raise|increase/i }).first();
    await up.click(); step();
    await expect(page.getByText(/override|changed|level/i).first()).toBeVisible();
    return why.includes("reason") || why.includes("Reason") ? "adjustment reasons shown" : "no visible reason text";
  });

  writeFileSync(`${OUT}/walkthrough.json`, JSON.stringify(rows, null, 2));
});
