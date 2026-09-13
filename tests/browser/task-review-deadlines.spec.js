import {test, expect} from "./control-audit.js";
import {TASK_FORM_COPY} from "../../custom_components/family_assistant/frontend/task-form.js";
import {TASK_ITEM_COPY} from "../../custom_components/family_assistant/frontend/task-items.js";

const addLabel = {en: "Add", ru: "Добавить", uk: "Додати"};
const createForm = page => page.locator("form[data-task-create]");
const taskItem = page => page.locator(".body > ul.list > li.item").first();
const submittedCalls = page => page.evaluate(() => window.calls);

async function open(page, {language = "en", actor = "owner", query = ""} = {}) {
  await page.goto(`/tests/fixtures/task-review-deadlines.html?lang=${language}&actor=${actor}${query}`);
  await expect(page.getByRole("button", {name: addLabel[language], exact: true})).toBeVisible();
}

async function beginCreate(page, language = "en") {
  await page.getByRole("button", {name: addLabel[language], exact: true}).click();
  const form = createForm(page);
  await form.locator('[name="title"]').fill("Synthetic review task");
  return form;
}

async function advanced(form) {
  await form.locator("details > summary").click();
}

async function beginEdit(page, language = "en") {
  await taskItem(page).getByRole("button", {name: TASK_ITEM_COPY[language].action_edit, exact: true}).click();
  const form = taskItem(page).locator("form");
  await advanced(form);
  return form;
}

for (const language of ["en", "ru", "uk"]) {
  test(`review deadline ${language}: parent creates, edits and disables through actual mobile controls`, async ({page}, testInfo) => {
    await page.setViewportSize({width: 390, height: 844});
    await open(page, {language, actor: "parent"});
    const form = await beginCreate(page, language);
    await form.locator('[name="assignee"]').selectOption("child");
    await advanced(form);
    const input = form.getByLabel(TASK_FORM_COPY[language].reviewMinutes, {exact: true});
    await expect(input).toHaveValue("0");
    await expect(input).toHaveAttribute("min", "0");
    await expect(input).toHaveAttribute("max", "10080");
    await expect(input).toHaveAttribute("step", "1");
    await input.fill("90");
    await page.screenshot({path: testInfo.outputPath(`review-create-${language}.png`), fullPage: true});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(await submittedCalls(page)).toEqual([]);
    await form.locator('button[type="submit"]').click();
    await expect(form).toHaveCount(0);
    const calls = await submittedCalls(page);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({action: "tasks.create", payload: {assignee: "child", assignee_revision: 1, review_minutes: 90}});
    expect(calls[0].payload).not.toHaveProperty("due_at");

    let editor = await beginEdit(page, language);
    const reviewLabel = TASK_ITEM_COPY[language].label_review_minutes;
    await expect(editor.getByLabel(reviewLabel, {exact: true})).toHaveValue("90");
    await editor.getByLabel(reviewLabel, {exact: true}).fill("120");
    await editor.getByRole("button", {name: TASK_ITEM_COPY[language].action_save, exact: true}).click();
    await expect(editor).toHaveCount(0);
    expect((await submittedCalls(page)).at(-1)).toMatchObject({action: "tasks.revise", payload: {id: "T000001", revision: 1, review_minutes: 120}});
    editor = await beginEdit(page, language);
    await expect(editor.getByLabel(reviewLabel, {exact: true})).toHaveValue("120");
    await editor.getByLabel(reviewLabel, {exact: true}).fill("0");
    await editor.getByRole("button", {name: TASK_ITEM_COPY[language].action_save, exact: true}).click();
    await expect(editor).toHaveCount(0);
    expect((await submittedCalls(page)).at(-1)).toMatchObject({action: "tasks.revise", payload: {revision: 2, review_minutes: 0}});
    expect(await page.evaluate(() => window.fixture.tasks[0].review_minutes)).toBe(0);
  });
}

test("default-off create and an untouched editor preserve omission", async ({page}) => {
  await open(page);
  const form = await beginCreate(page);
  await form.locator('button[type="submit"]').click();
  await expect(form).toHaveCount(0);
  expect((await submittedCalls(page))[0].payload).not.toHaveProperty("review_minutes");
  expect(await page.evaluate(() => window.fixture.tasks[0])).not.toHaveProperty("review_minutes");
  const editor = await beginEdit(page);
  await expect(editor.locator('[name="review_minutes"]')).toHaveValue("0");
  await editor.getByRole("button", {name: TASK_ITEM_COPY.en.action_save, exact: true}).click();
  await expect(editor).toHaveCount(0);
  expect((await submittedCalls(page)).at(-1).payload).not.toHaveProperty("review_minutes");
});

test("invalid create intervals make no request; failed save freezes and retries the original policy", async ({page}) => {
  await open(page, {language: "ru"});
  const form = await beginCreate(page, "ru");
  await advanced(form);
  const input = form.locator('[name="review_minutes"]');
  for (const value of ["-1", "10081", "1.5"]) {
    await input.fill(value);
    await form.locator('button[type="submit"]').click();
    expect(await input.evaluate(field => field.validity.valid)).toBe(false);
    expect(await submittedCalls(page)).toEqual([]);
  }
  await input.fill("60");
  await page.evaluate(() => { window.failCommand = true; });
  await form.locator('button[type="submit"]').click();
  await expect(form.locator('button[type="submit"]')).toHaveText(TASK_FORM_COPY.ru.retry);
  await expect(input).toBeDisabled();
  const first = (await submittedCalls(page))[0];
  expect(first.payload.review_minutes).toBe(60);
  expect(await page.evaluate(() => window.fixture.tasks)).toEqual([]);
  await page.evaluate(() => { window.failCommand = false; });
  await form.locator('button[type="submit"]').click();
  await expect(form).toHaveCount(0);
  expect((await submittedCalls(page))[1]).toEqual(first);
  expect(await page.evaluate(() => window.fixture.tasks)).toHaveLength(1);
});

test("editor bounds reject requests and failed save retries the same revision and policy", async ({page}) => {
  await open(page, {language: "uk", query: "&seed=1"});
  const form = await beginEdit(page, "uk");
  const input = form.locator('[name="review_minutes"]');
  for (const value of ["-1", "10081", "1.5"]) {
    await input.fill(value);
    await form.locator('button[type="submit"]').click();
    expect(await input.evaluate(field => field.validity.valid)).toBe(false);
    expect(await submittedCalls(page)).toEqual([]);
  }
  await input.fill("10080");
  await page.evaluate(() => { window.failCommand = true; });
  await form.locator('button[type="submit"]').click();
  await expect(form.getByRole("button", {name: TASK_ITEM_COPY.uk.action_retry, exact: true})).toBeEnabled();
  await expect(input).toBeDisabled();
  const first = (await submittedCalls(page))[0];
  expect(first).toMatchObject({action: "tasks.revise", payload: {revision: 1, review_minutes: 10080}});
  expect(await page.evaluate(() => window.fixture.tasks[0].review_minutes)).toBe(60);
  await page.evaluate(() => { window.failCommand = false; });
  await form.getByRole("button", {name: TASK_ITEM_COPY.uk.action_retry, exact: true}).click();
  await expect(form).toHaveCount(0);
  expect((await submittedCalls(page))[1]).toEqual(first);
  expect(await page.evaluate(() => window.fixture.tasks[0])).toMatchObject({revision: 2, review_minutes: 10080});
});

test("personal creation clears reviewer interval and personal editing offers no reviewer policy", async ({page}) => {
  await open(page, {language: "ru"});
  const form = await beginCreate(page, "ru");
  await advanced(form);
  await form.locator('[name="review_minutes"]').fill("90");
  await form.locator('[name="personal"]').check();
  await expect(form.locator('[name="review_minutes"]')).toBeDisabled();
  await expect(form.locator('[name="review_minutes"]')).toHaveValue("0");
  await expect(form.locator('[name="assignee"]')).toHaveValue("owner");
  await expect(form.locator('[name="report_type"]')).toHaveValue("none");
  await form.locator('button[type="submit"]').click();
  await expect(form).toHaveCount(0);
  expect((await submittedCalls(page))[0].payload).toMatchObject({personal: true, assignee: "owner", report_type: "none"});
  expect((await submittedCalls(page))[0].payload).not.toHaveProperty("review_minutes");
  const editor = await beginEdit(page, "ru");
  await expect(editor.locator('[name="review_minutes"]')).toHaveCount(0);
  await editor.getByRole("button", {name: TASK_ITEM_COPY.ru.action_save, exact: true}).click();
  await expect(editor).toHaveCount(0);
  expect((await submittedCalls(page)).at(-1).payload).not.toHaveProperty("review_minutes");
});

test("child creates only self work without reviewer policy", async ({page}) => {
  await open(page, {language: "uk", actor: "child"});
  const form = await beginCreate(page, "uk");
  await advanced(form);
  await expect(form.locator('[name="review_minutes"]')).toHaveCount(0);
  await expect(form.locator('[name="multi"]')).toHaveCount(0);
  await expect(form.locator('[name="assignee"] option')).toHaveCount(1);
  await expect(form.locator('[name="assignee"]')).toHaveValue("child");
  await form.locator('button[type="submit"]').click();
  await expect(form).toHaveCount(0);
  expect((await submittedCalls(page))[0].payload).not.toHaveProperty("review_minutes");
});

for (const actor of ["owner", "child"]) {
  test(`private task editor ${actor}: only a parent can alter the reviewer policy`, async ({page}) => {
    await open(page, {actor, query: "&seed=1&scope=private&own=1"});
    const editor = await beginEdit(page);
    const review = editor.locator('[name="review_minutes"]');
    if (actor === "owner") {
      await expect(review).toHaveValue("60");
      await review.fill("45");
    } else {
      await expect(review).toHaveCount(0);
      await editor.locator('[name="title"]').fill("Synthetic child correction");
    }
    await editor.getByRole("button", {name: TASK_ITEM_COPY.en.action_save, exact: true}).click();
    await expect(editor).toHaveCount(0);
    const call = (await submittedCalls(page))[0];
    expect(call.action).toBe("tasks.revise");
    if (actor === "owner") expect(call.payload.review_minutes).toBe(45);
    else expect(call.payload).not.toHaveProperty("review_minutes");
    expect(await page.evaluate(() => window.fixture.tasks[0])).toMatchObject({delivery_scope: "private", review_minutes: actor === "owner" ? 45 : 60});
  });
}

test("multi-person preview includes review interval and lost response retries one atomic batch", async ({page}) => {
  await open(page, {language: "uk"});
  const form = await beginCreate(page, "uk");
  await form.locator('[name="multi"]').check();
  for (const member of ["child", "sibling"]) await form.locator(`[name="assignee_multi"][value="${member}"]`).check();
  await advanced(form);
  await form.locator('[name="review_minutes"]').fill("120");
  await form.locator('button[type="submit"]').click();
  await expect(form.locator(".task-multi-review-preview")).toContainText(`${TASK_FORM_COPY.uk.reviewMinutes}: 120`);
  await expect(form.locator(".task-multi-review-preview")).toContainText("Child 1");
  await expect(form.locator(".task-multi-review-preview")).toContainText("Child 2");
  await expect(form.getByRole("button", {name: TASK_FORM_COPY.uk.applyBatch, exact: true})).toBeDisabled();
  expect(await submittedCalls(page)).toEqual([]);
  await form.locator('[name="confirm_batch"]').check();
  await page.evaluate(() => { window.loseReplyOnce = true; });
  await form.getByRole("button", {name: TASK_FORM_COPY.uk.applyBatch, exact: true}).click();
  await expect(form.getByRole("button", {name: TASK_FORM_COPY.uk.retry, exact: true})).toBeEnabled();
  const original = (await submittedCalls(page))[0];
  expect(original.action).toBe("batch");
  expect(original.payload.commands).toHaveLength(2);
  for (const command of original.payload.commands) expect(command).toMatchObject({action: "tasks.create", payload: {review_minutes: 120}});
  await form.getByRole("button", {name: TASK_FORM_COPY.uk.retry, exact: true}).click();
  await expect(form).toHaveCount(0);
  expect((await submittedCalls(page))[1]).toEqual(original);
  const tasks = await page.evaluate(() => window.fixture.tasks);
  expect(tasks).toHaveLength(2);
  expect(tasks.map(task => task.assignee)).toEqual(["child", "sibling"]);
  expect(new Set(tasks.map(task => task.id)).size).toBe(2);
});
