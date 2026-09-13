import {test, expect} from "./control-audit.js";
import {readFile} from "node:fs/promises";

test("mobile owner reviews complete deidentified JSON before a fresh local download", async ({page}) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/health-view.html?lang=ru&role=owner&diagnostics");
  await page.evaluate(()=>window.ready);
  const card=page.locator("family-health-card");
  await card.getByRole("button",{name:"Проверить технический отчёт",exact:true}).click();
  const preview=card.locator(".developer-json");
  await expect(preview).toContainText("provider_timeout");
  expect(await preview.textContent()).not.toContain("PRIVATE_");
  const pending=page.waitForEvent("download");
  await card.getByRole("button",{name:"Скачать проверенный JSON",exact:true}).click();
  const download=await pending;
  expect(download.suggestedFilename()).toBe("family-assistant-technical-report.json");
  const text=await readFile(await download.path(),"utf8");
  expect(JSON.parse(text)).toEqual(await page.evaluate(()=>window.technicalReport));
  expect(text).not.toContain("PRIVATE_");
  expect(await page.evaluate(()=>window.calls.length)).toBe(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:"test-results/developer-report-ru.png",fullPage:true});
});

test("report drift removes the old preview without exporting a different report", async ({page}) => {
  await page.goto("/tests/fixtures/health-view.html?lang=en&role=owner&diagnostics");
  await page.evaluate(()=>window.ready);
  const card=page.locator("family-health-card");
  await card.getByRole("button",{name:"Review technical report",exact:true}).click();
  await expect(card.locator(".developer-json")).toBeVisible();
  await page.evaluate(()=>window.technicalReport.cases[0].count++);
  let downloads=0;page.on("download",()=>downloads++);
  await card.getByRole("button",{name:"Download reviewed JSON",exact:true}).click();
  await expect(card.locator(".developer-json")).toHaveCount(0);
  await expect(card.locator(".developer-view")).toContainText("report or access changed");
  expect(downloads).toBe(0);
});
