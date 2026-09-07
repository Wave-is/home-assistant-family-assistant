import { test, expect } from "@playwright/test";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
  "base64",
);

async function choosePhoto(page, card, name = "reviewed.png") {
  const section = card.locator('[data-task-media-id="T000001"]');
  await section.locator('input[type="file"]').setInputFiles({
    name,
    mimeType: "image/png",
    buffer: PNG,
  });
  await section
    .getByRole("button", { name: /Review selected photo|Проверить выбранное фото|Перевірити вибране фото/ })
    .click();
  return section;
}

async function confirmUpload(section, label) {
  await section.locator('[name="confirm_upload"]').check();
  await section.getByRole("button", { name: label, exact: true }).click();
}

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-09-07T07:00:00Z"));
});

test("English photo upload is reviewed and attached only by a separate submit", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  const card = page.locator("family-assistant-card");
  const section = await choosePhoto(page, card, "private-report.png");
  const review = section.locator(".task-media-review");
  await expect(review).toContainText("private-report.png");
  await expect(review).toContainText("not sent to Telegram");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  expect(await page.evaluate(() => window.httpCalls.length)).toBe(0);

  await confirmUpload(section, "Reserve and upload");
  await expect(section).toContainText(
    "The verified photo is ready. Submitting it is a separate action.",
  );
  let state = await page.evaluate(() => ({
    task: window.fixture.tasks.find((item) => item.id === "T000001"),
    calls: window.calls,
    http: window.httpCalls,
    media: [...window.fixture.media.values()].map(({ body, ...item }) => ({
      ...item,
      bytes: body?.length,
    })),
  }));
  expect(state.task.status).toBe("assigned");
  expect(state.task.revision).toBe(1);
  expect(state.task.report_attachments).toEqual([]);
  expect(state.calls).toHaveLength(1);
  expect(state.calls[0]).toMatchObject({
    action: "media.reserve",
    payload: {
      purpose: "task_report",
      task_id: "T000001",
      task_revision: 1,
      uploader_revision: 3,
    },
  });
  expect(state.http).toHaveLength(1);
  expect(state.http[0]).toMatchObject({
    user_id: "ha-child",
    method: "PUT",
    revision: 1,
    content_type: "image/png",
    body: [...PNG],
  });
  expect(state.media.at(-1)).toMatchObject({
    revision: 2,
    status: "available",
    mime_type: "image/png",
    bytes: PNG.length,
  });

  await section.locator('[name="confirm_submit"]').check();
  await section
    .getByRole("button", { name: "Submit photo report", exact: true })
    .click();
  await expect(section).toContainText("Current report photo");
  state = await page.evaluate(() => ({
    task: window.fixture.tasks.find((item) => item.id === "T000001"),
    calls: window.calls,
    media: [...window.fixture.media.values()].at(-1),
  }));
  expect(state.task).toMatchObject({ status: "submitted", revision: 2 });
  expect(state.task.report_attachments).toHaveLength(1);
  expect(state.media).toMatchObject({ status: "attached", revision: 3 });
  expect(state.calls).toHaveLength(2);
  expect(state.calls[1]).toMatchObject({
    action: "tasks.submit",
    payload: {
      id: "T000001",
      revision: 1,
      media: { id: state.media.id, revision: 2 },
    },
  });
});

test("Russian narrow upload retries the exact committed PUT without another reservation", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/task-media-fixture.html?lang=ru&actor=child");
  const card = page.locator("family-assistant-card");
  const section = await choosePhoto(page, card, "личный-отчёт.png");
  await page.evaluate(() => (window.losePut = true));
  await confirmUpload(section, "Зарезервировать и загрузить");
  await expect(
    section.getByRole("button", { name: "Повторить точную загрузку", exact: true }),
  ).toBeVisible();
  let attempts = await page.evaluate(() => ({
    calls: window.calls,
    http: window.httpCalls,
    media: [...window.fixture.media.values()].at(-1),
  }));
  expect(attempts.calls).toHaveLength(1);
  expect(attempts.http).toHaveLength(1);
  expect(attempts.media).toMatchObject({ status: "available", revision: 2 });
  await page.screenshot({
    path: "test-results/task-media-upload-retry-ru.png",
    fullPage: true,
  });
  await confirmUpload(section, "Повторить точную загрузку");
  await expect(section).toContainText("Проверенное фото готово");
  attempts = await page.evaluate(() => ({
    calls: window.calls,
    http: window.httpCalls,
    count: window.fixture.media.size,
  }));
  expect(attempts.calls).toHaveLength(1);
  expect(attempts.http).toHaveLength(2);
  expect(attempts.http[1]).toEqual(attempts.http[0]);
  expect(attempts.count).toBe(2);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
});

test("Ukrainian lost submit retries one frozen command after the attachment appears", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/task-media-fixture.html?lang=uk&actor=child");
  const card = page.locator("family-assistant-card");
  const section = await choosePhoto(page, card, "звіт.png");
  await confirmUpload(section, "Зарезервувати й завантажити");
  await section.locator('[name="confirm_submit"]').check();
  await page.evaluate(() => (window.loseSubmit = true));
  await section
    .getByRole("button", { name: "Надіслати фотозвіт", exact: true })
    .click();
  const retry = section.getByRole("button", {
    name: "Повторити точне надсилання",
    exact: true,
  });
  await expect(retry).toBeVisible();
  await expect(section.locator('[name="confirm_submit"]')).toBeChecked();
  await expect(section.locator('[name="confirm_submit"]')).toBeDisabled();
  let state = await page.evaluate(() => ({
    task: window.fixture.tasks.find((item) => item.id === "T000001"),
    calls: window.calls,
    mediaCount: window.fixture.media.size,
  }));
  expect(state.task).toMatchObject({ status: "submitted", revision: 2 });
  expect(state.task.report_attachments).toHaveLength(1);
  expect(state.calls.filter((call) => call.action === "tasks.submit")).toHaveLength(1);
  await page.screenshot({
    path: "test-results/task-media-submit-retry-uk.png",
    fullPage: true,
  });
  await retry.click();
  await expect(retry).toHaveCount(0);
  state = await page.evaluate(() => ({
    task: window.fixture.tasks.find((item) => item.id === "T000001"),
    calls: window.calls.filter((call) => call.action === "tasks.submit"),
    mediaCount: window.fixture.media.size,
  }));
  expect(state.calls).toHaveLength(2);
  expect(state.calls[1]).toEqual(state.calls[0]);
  expect(state.task.report_attachments).toHaveLength(1);
  expect(state.mediaCount).toBe(2);
});

test("failed refresh after a committed PUT hides all data then restores the exact retry", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  const card = page.locator("family-assistant-card");
  let section = await choosePhoto(page, card, "hidden-during-error.png");
  await page.evaluate(() => {
    window.losePut = true;
    window.failNextView = true;
  });
  await confirmUpload(section, "Reserve and upload");
  await expect(card.getByRole("alert")).toBeVisible();
  await expect(card.getByRole("button", { name: "Try again", exact: true })).toBeVisible();
  await expect(card).not.toContainText("Synthetic family");
  await expect(card).not.toContainText("Private photo task");
  await expect(card).not.toContainText("hidden-during-error.png");
  await expect(card.locator(".task-media")).toHaveCount(0);
  let attempts = await page.evaluate(() => ({
    calls: window.calls,
    http: window.httpCalls,
    media: [...window.fixture.media.values()].at(-1),
  }));
  expect(attempts.calls).toHaveLength(1);
  expect(attempts.http).toHaveLength(1);
  expect(attempts.media).toMatchObject({ status: "available", revision: 2 });

  await card.getByRole("button", { name: "Try again", exact: true }).click();
  section = card.locator('[data-task-media-id="T000001"]');
  await expect(
    section.getByRole("button", { name: "Retry exact upload", exact: true }),
  ).toBeVisible();
  await confirmUpload(section, "Retry exact upload");
  await expect(section).toContainText("The verified photo is ready");
  attempts = await page.evaluate(() => ({
    calls: window.calls,
    http: window.httpCalls,
    count: window.fixture.media.size,
  }));
  expect(attempts.calls).toHaveLength(1);
  expect(attempts.http).toHaveLength(2);
  expect(attempts.http[1]).toEqual(attempts.http[0]);
  expect(attempts.count).toBe(2);
});

test("reviewed files are discarded on user, entry, member epoch, and task changes", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  let card = page.locator("family-assistant-card");
  let section = await choosePhoto(page, card, "user-bound.png");
  await page.evaluate(() => window.setActor("sibling"));
  await expect(section).toHaveCount(0);
  await expect(card).toContainText("SIBLING PRIVATE PHOTO TASK");
  await expect(card).not.toContainText("Private photo task");
  expect(await page.evaluate(() => ({ calls: window.calls.length, http: window.httpCalls.length })))
    .toEqual({ calls: 0, http: 0 });

  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  card = page.locator("family-assistant-card");
  section = await choosePhoto(page, card, "entry-bound.png");
  await page.evaluate(() => window.setEntry("another-household"));
  await expect(section).toHaveCount(0);
  expect(await page.evaluate(() => ({ calls: window.calls.length, http: window.httpCalls.length })))
    .toEqual({ calls: 0, http: 0 });

  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  card = page.locator("family-assistant-card");
  section = await choosePhoto(page, card, "epoch-bound.png");
  await page.evaluate(async () => {
    window.fixture.members.find((member) => member.id === "child").revision = 4;
    await window.syncCard();
  });
  await expect(section.locator(".task-media-review")).toHaveCount(0);
  expect(await page.evaluate(() => ({ calls: window.calls.length, http: window.httpCalls.length })))
    .toEqual({ calls: 0, http: 0 });

  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  card = page.locator("family-assistant-card");
  section = await choosePhoto(page, card, "role-bound.png");
  await page.evaluate(async () => {
    window.fixture.members.find((member) => member.id === "child").role = "guest";
    await window.syncCard();
  });
  await expect(section).toHaveCount(0);
  expect(await page.evaluate(() => ({ calls: window.calls.length, http: window.httpCalls.length })))
    .toEqual({ calls: 0, http: 0 });

  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  card = page.locator("family-assistant-card");
  section = await choosePhoto(page, card, "task-bound.png");
  await page.evaluate(async () => {
    window.fixture.tasks.find((item) => item.id === "T000001").revision = 2;
    await window.syncCard();
  });
  await expect(section.locator(".task-media-review")).toHaveCount(0);
  expect(await page.evaluate(() => ({ calls: window.calls.length, http: window.httpCalls.length })))
    .toEqual({ calls: 0, http: 0 });
});

test("parent explicitly loads history and every hidden preview revokes its Blob URL", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=parent");
  const card = page.locator("family-assistant-card");
  const item = card.locator("li.item").filter({ hasText: "Private prior photo task" });
  const previous = item.locator(".task-media-attachment").filter({
    hasText: "Previous report photo",
  });
  await expect(previous.locator("img")).toHaveCount(0);
  expect(await page.evaluate(() => window.httpCalls.length)).toBe(0);
  await previous.getByRole("button", { name: "Load photo", exact: true }).click();
  await expect(previous.locator("img")).toBeVisible();
  let state = await page.evaluate(() => ({
    http: window.httpCalls,
    urls: window.objectUrls.size,
  }));
  expect(state.http).toHaveLength(1);
  expect(state.http[0]).toMatchObject({
    user_id: "ha-parent",
    method: "GET",
    revision: 3,
  });
  expect(state.urls).toBe(1);
  await previous.getByRole("button", { name: "Hide photo", exact: true }).click();
  state = await page.evaluate(() => ({
    urls: window.objectUrls.size,
    revoked: window.revokedUrls.length,
  }));
  expect(state).toEqual({ urls: 0, revoked: 1 });

  await previous.getByRole("button", { name: "Load photo", exact: true }).click();
  await expect(previous.locator("img")).toBeVisible();
  await page.evaluate(() => window.setActor("child"));
  await expect(card).not.toContainText("Previous report photo");
  await expect(card).not.toContainText("SIBLING PRIVATE PHOTO TASK");
  state = await page.evaluate(() => ({
    urls: window.objectUrls.size,
    revoked: window.revokedUrls.length,
  }));
  expect(state).toEqual({ urls: 0, revoked: 2 });
});
