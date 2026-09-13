import {test, expect} from "./control-audit.js";
import {HOME_STATUS_COPY} from "../../custom_components/family_assistant/frontend/home-status-copy.js";

const section = page => page.locator(".home-status");
const sourceCalls = page => page.evaluate(() => window.calls.filter(row => row.type === "family_assistant/home_status").length);
async function open(page, query = "") {
  await page.goto(`/tests/fixtures/home-status.html?${query}`);
  await expect(section(page)).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.card._loading)).toBe(false);
}

for (const language of ["en", "ru", "uk"]) {
  test(`home status ${language}: localized mobile read, usable group key and explicit refresh`, async ({page}, testInfo) => {
    await page.setViewportSize({width: 390, height: 844});
    await open(page, `lang=${language}`);
    const view = section(page), t = HOME_STATUS_COPY[language];
    await expect(view).toContainText("-2500 W");
    await expect(view).toContainText(`${t.reported}: ${t.state_on}`);
    await expect(view).toContainText("Synthetic room (room)");
    await expect(view).toContainText(t.manual);
    await expect(view.locator("a,img,iframe")).toHaveCount(0);
    await page.screenshot({path: testInfo.outputPath(`home-status-${language}.png`), fullPage: true});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await sourceCalls(page)).toBe(1);
    await page.evaluate(() => {window.readings.energy[1].value = 1750;});
    await view.getByRole("button", {name: t.refresh, exact: true}).click();
    await expect(view).toContainText("1750 W");
    await expect(view).not.toContainText("-2500 W");
    expect(await sourceCalls(page)).toBe(2);
    expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
  });
}

test("the real idle timer checks revocation metadata, never polls sources", async ({page}) => {
  await page.clock.install();
  await open(page);
  expect(await sourceCalls(page)).toBe(1);
  const count = await page.evaluate(() => window.calls.length);
  await page.clock.runFor(31000);
  expect(await page.evaluate(() => window.calls.length)).toBeGreaterThanOrEqual(count + 3);
  expect(await sourceCalls(page)).toBe(1);
  await page.evaluate(() => {window.fixture.home_status_access = "synthetic-replaced-registry";});
  await page.clock.runFor(10000);
  await expect(section(page)).not.toContainText("Synthetic power");
  expect(await sourceCalls(page)).toBe(1);
  await page.evaluate(() => {window.readings.access_marker = window.fixture.home_status_access;});
  await section(page).getByRole("button", {name: HOME_STATUS_COPY.en.refresh, exact: true}).click();
  await expect(section(page)).toContainText("Synthetic power");
  expect(await sourceCalls(page)).toBe(2);
});

for (const query of ["role=guest", "disabled=1"]) {
  test(`home status ${query}: unavailable without a source request`, async ({page}) => {
    await open(page, query);
    expect(await sourceCalls(page)).toBe(0);
    await expect(page.locator("body")).not.toContainText("Synthetic power");
  });
}

test("permission/configuration revocation clears existing values without a new read", async ({page}) => {
  await open(page);
  await expect(section(page)).toContainText("Synthetic power");
  await page.evaluate(async () => {window.fixture.home_status_access = null; await window.card.refresh();});
  await expect(section(page)).not.toContainText("Synthetic power");
  expect(await sourceCalls(page)).toBe(1);
});

test("failed manual read clears stale values and hides exception content", async ({page}) => {
  await open(page);
  await page.evaluate(() => {window.failRead = true;});
  await section(page).getByRole("button", {name: HOME_STATUS_COPY.en.refresh, exact: true}).click();
  await expect(section(page)).toContainText(HOME_STATUS_COPY.en.unavailable);
  await expect(section(page)).not.toContainText("Synthetic power");
  await expect(page.locator("body")).not.toContainText("PRIVATE_EXCEPTION_CANARY");
  expect(await sourceCalls(page)).toBe(2);
});

test("bad/stale/restored data are labeled, never rendered as zero or markup", async ({page}) => {
  await open(page, "lang=uk");
  await page.evaluate(async () => {
    window.readings.energy[0] = {...window.readings.energy[0], value: null, quality: "invalid_unit"};
    window.readings.energy[1] = {...window.readings.energy[1], value: null, quality: "stale", report_age_seconds: 301};
    window.readings.groups[0].title = "<img src=x onerror=bad>";
    window.readings.groups[0].rows[0] = {...window.readings.groups[0].rows[0], value: null, quality: "restored"};
    window.card._homeStatusRequested = true; await window.card.refresh();
  });
  const t = HOME_STATUS_COPY.uk;
  for (const key of ["invalid_unit", "stale", "restored"]) await expect(section(page)).toContainText(t[key]);
  await expect(section(page)).not.toContainText("-2500 W");
  await expect(section(page).locator("img")).toHaveCount(0);
});

test("a late read cannot repopulate a replacement household", async ({page}) => {
  await open(page);
  await page.evaluate(() => {window.deferRead = true;});
  await section(page).getByRole("button", {name: HOME_STATUS_COPY.en.refresh, exact: true}).click();
  await expect.poll(() => page.evaluate(() => typeof window.resolveRead)).toBe("function");
  await page.evaluate(() => {
    window.card._hass = null;
    window.card.setConfig({entry_id: "synthetic-replacement", view: "home_status"});
    window.resolveRead(structuredClone(window.readings));
  });
  await expect.poll(() => page.evaluate(() => window.card._homeStatus)).toBe(null);
  await expect(page.locator("body")).not.toContainText("Synthetic power");
});
