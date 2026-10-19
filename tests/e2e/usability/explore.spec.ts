// Captures the instructor pages a first-time user meets (usability walkthrough, not a CI test).
import { test } from "@playwright/test";

import { newUserPage } from "../specs/helpers";

const OUT = process.env.UX_OUT ?? "ux-shots";

test("instructor pages", async ({ browser }) => {
  const page = await newUserPage(browser, "instructor");
  const shot = (name: string) => page.screenshot({ path: `${OUT}/${name}.png`, fullPage: true });
  await shot("01-home");
  for (const [name, path] of [
    ["02-scenarios", "/instructor/scenarios"],
    ["03-assign-new", "/instructor/assignments/new"],
    ["04-assignments", "/instructor/assignments"],
    ["05-sessions", "/instructor/sessions"],
    ["06-analytics", "/instructor/analytics"],
  ] as const) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    await shot(name);
  }
  await page.goto("/instructor/sessions");
  await page.waitForLoadState("networkidle");
  const firstResult = page.getByRole("link", { name: /result|open|review/i }).first();
  if (await firstResult.count()) {
    await firstResult.click();
    await page.waitForLoadState("networkidle");
    await shot("07-result");
  }
});
