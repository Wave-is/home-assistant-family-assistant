import { test, expect } from "@playwright/test";
import { SCHOOL_IMPORT_COPY } from "../../custom_components/family_assistant/frontend/school-import-copy.js";
import { SCHOOL_COPY } from "../../custom_components/family_assistant/frontend/school-copy.js";

for (const language of ["en", "ru", "uk"]) {
  test(`Calendar import stays unsaved until exact review (${language})`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`/tests/fixtures/school.html?lang=${language}`);
    await page.evaluate(() => {
      const original = window.card._hass.callWS;
      window.calendarReads = [];
      window.card._hass.callWS = async (message) => {
        if (message.type !== "family_assistant/school_calendar_preview") return original(message);
        window.calendarReads.push(message);
        return { saved: false, timezone: "Europe/Kyiv", valid_from: "2026-09-07", valid_until: "2026-09-13", count: 1,
          lessons: [{ weekday: 0, start: "09:00", end: "09:45", subject: "<script>Fictional calendar lesson</script>", room: "12", materials: [] }] };
      };
    });
    const card = page.locator("family-school-card");
    await card.getByRole("button", { name: SCHOOL_COPY[language].new_timetable, exact: true }).click();
    let form = card.locator('[data-school-form="edit"]');
    await form.locator('[name="title"]').fill("Reviewed single calendar week");
    await form.locator('[name="calendar_entity"]').fill("calendar.school");
    await form.locator('[name="calendar_week"]').fill("2026-09-07");
    await form.getByRole("button", { name: SCHOOL_IMPORT_COPY[language].load, exact: true }).click();
    await expect(form).toContainText(SCHOOL_IMPORT_COPY[language].loaded);
    await expect(form.locator('[name="valid_until"]')).toHaveValue("2026-09-13");
    await expect(form.locator('[name="subject"]')).toHaveValue("<script>Fictional calendar lesson</script>");
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
    expect(await page.evaluate(() => window.calendarReads.length)).toBe(1);
    await form.locator('button[type="submit"]').click();
    form = card.locator('[data-school-form="review"]');
    await expect(form).toContainText("Fictional calendar lesson");
    await expect(form.locator("script")).toHaveCount(0);
    expect(await page.evaluate(() => window.calls.length)).toBe(0);
    if (language === "uk") await page.screenshot({ path: "test-results/school-calendar-import-uk.png", fullPage: true });
    await form.locator('[name="reviewed"]').check();
    await form.locator('button[type="submit"]').click();
    await expect(form).toHaveCount(0);
    const calls = await page.evaluate(() => window.calls);
    expect(calls).toHaveLength(1);
    expect(calls[0].action).toBe("school.timetable_save");
    expect(calls[0].payload.valid_until).toBe("2026-09-13");
    expect(calls[0].payload.member).toBe("sibling");
  });
}

test("Calendar read cannot apply after parent loses authority", async ({ page }) => {
  await page.goto("/tests/fixtures/school.html");
  await page.evaluate(() => {
    const original = window.card._hass.callWS;
    window.card._hass.callWS = (message) => message.type === "family_assistant/school_calendar_preview" ?
      new Promise((resolve) => { window.finishCalendarRead = resolve; }) : original(message);
  });
  const card = page.locator("family-school-card");
  await card.getByRole("button", { name: "New timetable", exact: true }).click();
  const form = card.locator('[data-school-form="edit"]');
  await form.locator('[name="calendar_entity"]').fill("calendar.school");
  await form.locator('[name="calendar_week"]').fill("2026-09-07");
  await form.getByRole("button", { name: "Load into draft", exact: true }).click();
  await page.evaluate(async () => {
    window.fixture.role = "adult";
    window.fixture.members[0].role = "adult";
    window.fixture.members[0].revision++;
    await window.card.refresh();
    window.finishCalendarRead({ saved: false, timezone: "Europe/Kyiv", valid_from: "2026-09-07", valid_until: "2026-09-13", count: 1,
      lessons: [{ weekday: 0, start: "09:00", end: "09:45", subject: "Private delayed lesson", room: "", materials: [] }] });
  });
  await expect(card.locator(".school-section")).toHaveCount(0);
  await expect(card).not.toContainText("Private delayed lesson");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-09-07T07:00:00Z"));
});

test("Stale pinned routine needs explicit removal or replacement before a title edit", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/school.html");
  await page.evaluate(async () => {
    window.fixture.routines.templates[0].revision++;
    await window.card.refresh();
  });
  const card = page.locator("family-school-card");
  await card
    .getByRole("button", { name: "Edit timetable", exact: true })
    .click();
  const form = card.locator('[data-school-form="edit"]');
  await form
    .locator('[name="title"]')
    .fill("Renamed without silently dropping a link");
  await expect(form).toContainText(
    "This saved routine version is no longer available",
  );
  await expect(form.locator('[name="backpack_routine"]')).toHaveValue(
    "__unavailable__",
  );
  await form.locator('button[type="submit"]').click();
  await expect(card.locator('[data-school-form="review"]')).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await form.locator('[name="backpack_routine"]').selectOption("");
  await form.locator('button[type="submit"]').click();
  const review = card.locator('[data-school-form="review"]');
  await expect(review).toBeVisible();
  await review.locator('[name="reviewed"]').check();
  await review.locator('button[type="submit"]').click();
  await expect(review).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].payload.backpack_routine).toBeNull();
});

test("Committed lost response retains exact operation after child and routine revisions advance", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/school.html");
  const card = page.locator("family-school-card");
  await card
    .getByRole("button", { name: "Edit timetable", exact: true })
    .click();
  const form = card.locator('[data-school-form="edit"]');
  await form.locator('[name="title"]').fill("Committed reviewed timetable");
  await form.locator('button[type="submit"]').click();
  const review = card.locator('[data-school-form="review"]');
  await review.locator('[name="reviewed"]').check();
  await page.evaluate(() => (window.loseResponse = true));
  await review.locator('button[type="submit"]').click();
  await expect(
    review.getByRole("button", { name: "Retry exact request" }),
  ).toBeVisible();
  await page.evaluate(async () => {
    window.fixture.members[1].revision++;
    window.fixture.routines.templates[0].revision++;
    await window.card.refresh();
  });
  await expect(review).toBeVisible();
  await review.locator('button[type="submit"]').click();
  await expect(review).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload.member_revision).toBe(1);
  expect(calls[0].payload.backpack_routine).toEqual({ id: "R1", revision: 1 });
  expect(
    await page.evaluate(() => window.fixture.school.timetables[0].revision),
  ).toBe(2);
});

test("RU timetable edit reviews exact child and fields, retries lost receipt once", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/school.html?lang=ru");
  const card = page.locator("family-school-card");
  await card
    .locator('[data-school-timetable="ST000001"]')
    .getByRole("button", { name: "Изменить расписание" })
    .click();
  const form = card.locator('[data-school-form="edit"]');
  await form.locator('[name="title"]').fill("Осень — проверенное расписание");
  await form.locator('[name="materials"]').fill("Тетрадь\nЛинейка");
  await form.locator('[name="exceptions"]').fill("2026-09-14\n2026-09-21");
  await page.screenshot({
    path: "test-results/school-edit-ru.png",
    fullPage: true,
  });
  await form.locator('button[type="submit"]').click();
  const review = card.locator('[data-school-form="review"]');
  await expect(review).toContainText("Sam");
  await expect(review).toContainText("Линейка");
  await expect(review).toContainText("2026-09-21");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await page.screenshot({
    path: "test-results/school-review-ru.png",
    fullPage: true,
  });
  await review.locator('[name="reviewed"]').check();
  await page.evaluate(() => (window.loseResponse = true));
  await review.locator('button[type="submit"]').click();
  await expect(
    review.getByRole("button", { name: "Повторить тот же запрос" }),
  ).toBeVisible();
  await page.evaluate(
    () => (window.card._pending = { id: "unrelated", fingerprint: "other" }),
  );
  await review.locator('button[type="submit"]').click();
  await expect(review).toHaveCount(0);
  const calls = await page.evaluate(() => window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload.member_revision).toBe(1);
  expect(calls[0].payload.revision).toBe(1);
  expect(calls[0].payload.backpack_routine).toEqual({ id: "R1", revision: 1 });
  expect(
    await page.evaluate(() => window.fixture.school.timetables[0].revision),
  ).toBe(2);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});

test("UK child reads materials without controls and revision change clears focused private DOM", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tests/fixtures/school.html?lang=uk&actor=child");
  const card = page.locator("family-school-card");
  await expect(card).toContainText("Notebook");
  await expect(
    card.getByRole("button", {
      name: /Новий розклад|Змінити розклад|Архівувати розклад/,
    }),
  ).toHaveCount(0);
  await page.screenshot({
    path: "test-results/school-child-uk.png",
    fullPage: true,
  });
  await page.evaluate(async () => {
    const f = document.createElement("form"),
      i = document.createElement("input");
    f.append(i);
    window.card.shadowRoot.append(f);
    i.focus();
    window.fixture.members[1].revision++;
    await window.card.refresh();
  });
  await expect(card).not.toContainText("Notebook");
  await expect(card.locator("[data-school-upcoming]")).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("Current routine revision change rejects detached school review without writing", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/school.html");
  const card = page.locator("family-school-card");
  await card
    .getByRole("button", { name: "Edit timetable", exact: true })
    .click();
  const edit = card.locator('[data-school-form="edit"]');
  await edit.locator('[name="title"]').fill("Changed title");
  await edit.locator('button[type="submit"]').click();
  const review = card.locator('[data-school-form="review"]');
  await expect(review).toBeVisible();
  await page.evaluate(async () => {
    window.oldReview = window.card.shadowRoot.querySelector(
      '[data-school-form="review"]',
    );
    window.oldReview.querySelector("input").focus();
    window.fixture.routines.templates[0].revision++;
    await window.card.refresh();
    window.oldReview.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
  });
  await expect(review).toHaveCount(0);
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
});

test("Archive is a named reviewed action and leaves parent history", async ({
  page,
}) => {
  await page.goto("/tests/fixtures/school.html");
  const card = page.locator("family-school-card");
  await card
    .getByRole("button", { name: "Archive timetable", exact: true })
    .click();
  const edit = card.locator('[data-school-form="archive_edit"]');
  await edit.locator('[name="reason"]').fill("New term");
  await edit.locator('button[type="submit"]').click();
  const review = card.locator('[data-school-form="archive_review"]');
  await expect(review).toContainText("Sam");
  await expect(review).toContainText("New term");
  expect(await page.evaluate(() => window.calls.length)).toBe(0);
  await review.locator('[name="reviewed"]').check();
  await review.locator('button[type="submit"]').click();
  await expect(review).toHaveCount(0);
  expect(
    await page.evaluate(() => window.fixture.school.timetables[0].status),
  ).toBe("archived");
  expect(
    await page.evaluate(
      () => window.fixture.school.timetables[0].history.at(-1).reason,
    ),
  ).toBe("New term");
});
