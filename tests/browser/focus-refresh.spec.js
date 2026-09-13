import { expect, test } from "./control-audit.js";

const card = (page) => page.locator("family-tasks-card");

async function activeText(page) {
  return page.evaluate(
    () => window.card.shadowRoot.activeElement?.textContent || null,
  );
}

test("passive refresh restores a unique action button and archive summary", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/focus-refresh.html?view=tasks");
  const taskCard = card(page);
  const add = taskCard.locator(".toolbar button");
  await add.focus();
  await page.evaluate(() => window.refreshDone());
  await expect(taskCard.locator(".toolbar button")).toBeFocused();

  const details = taskCard.locator("details.tasks-archive");
  const summary = details.locator("summary");
  await summary.click();
  await summary.focus();
  await page.evaluate(() => window.refreshDone());
  await expect(taskCard.locator("details.tasks-archive")).toHaveAttribute(
    "open",
    "",
  );
  await expect(taskCard.locator("details.tasks-archive summary")).toBeFocused();
});

test("latest in-card focus wins and focus moved outside is not reclaimed", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/focus-refresh.html?view=tasks");
  const taskCard = card(page);
  await taskCard.locator(".toolbar button").focus();
  await page.evaluate(() => {
    window.deferNextView();
    window.pendingRefresh = window.refreshDone();
  });
  await taskCard.locator("details.tasks-archive summary").focus();
  await page.evaluate(async () => {
    window.releaseView();
    await window.pendingRefresh;
  });
  await expect(taskCard.locator("details.tasks-archive summary")).toBeFocused();

  await taskCard.locator(".toolbar button").focus();
  await page.evaluate(() => {
    window.deferNextView();
    window.pendingRefresh = window.refreshDone();
  });
  await page.locator("#outside").focus();
  await page.evaluate(async () => {
    window.releaseView();
    await window.pendingRefresh;
  });
  await expect(page.locator("#outside")).toBeFocused();
  expect(await activeText(page)).toBeNull();
});

test("focused radio remains selected because focused forms are not replaced", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/focus-refresh.html?view=polls");
  const pollCard = page.locator("family-polls-card");
  await pollCard.getByRole("button", { name: "Vote", exact: true }).click();
  const radio = pollCard.locator('input[type="radio"][value="O2"]');
  await radio.check();
  const marker = await radio.evaluate((element) => {
    element.dataset.liveMarker = "same-node";
    return element.dataset.liveMarker;
  });
  expect(marker).toBe("same-node");
  await page.evaluate(() => window.refreshDone());
  await expect(radio).toBeChecked();
  await expect(radio).toBeFocused();
  expect(await radio.getAttribute("data-live-marker")).toBe("same-node");
  expect(await page.evaluate(() => window.calls.length)).toBe(2);
});

test("ambiguous controls and authority changes fail safe", async ({ page }) => {
  await page.goto("/tests/fixtures/focus-refresh.html?view=tasks");
  const taskCard = card(page);
  await page.evaluate(() => {
    const original = window.card.shadowRoot.querySelector(".toolbar button");
    original.after(original.cloneNode(true));
    original.focus();
  });
  await page.evaluate(() => window.refreshDone());
  expect(await activeText(page)).toBeNull();

  for (const kind of ["revision", "module", "role"]) {
    await page.reload();
    await taskCard.locator(".toolbar button").focus();
    await page.evaluate(() => {
      window.deferNextView();
      window.pendingRefresh = window.refreshDone();
    });
    await page.evaluate(async (change) => {
      window.revoke(change);
      window.releaseView();
      await window.pendingRefresh;
    }, kind);
    expect(await activeText(page)).toBeNull();
  }
});
