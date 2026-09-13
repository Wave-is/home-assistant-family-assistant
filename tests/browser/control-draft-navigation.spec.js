import {test, expect} from "./control-audit.js";
import {FAULT_PHOTO_COPY} from "../../custom_components/family_assistant/frontend/fault-photo-copy.js";

const calls = page => page.evaluate(() => window.calls);
const cancel = form => form.getByRole("button", {name: "Cancel", exact: true}).click();
// Exercise the form's alternate native submission path, not its button callback.
// requestSubmit emits the browser's submit event and retains HTML validation.
const submitForm = form => form.evaluate(node => node.requestSubmit());

test("draft navigation: pantry new and stock Cancel discard only unsaved values", async ({page}) => {
  await page.goto("/tests/fixtures/pantry.html?actor=parent");
  let card = page.locator("family-pantry-card");
  await card.getByRole("button", {name: "Add pantry item", exact: true}).click();
  await card.getByLabel("Item name", {exact: true}).fill("Unsent pantry draft");
  await cancel(card.locator("form"));
  await expect(card.locator("form")).toHaveCount(0);
  expect(await calls(page)).toEqual([]);
  await card.getByRole("button", {name: "Add pantry item", exact: true}).click();
  await expect(card.getByLabel("Item name", {exact: true})).toHaveValue("");
  expect(await page.evaluate(() => window.fixture.pantry.items)).toEqual([]);
  await cancel(card.locator("form"));
  await page.goto("/tests/fixtures/pantry.html?actor=adult");
  card = page.locator("family-pantry-card");
  await card.getByRole("button", {name: "Set stock", exact: true}).click();
  await card.getByLabel("Current quantity", {exact: true}).fill("17");
  await card.getByLabel("Reason for change", {exact: true}).fill("Unsent recount");
  await cancel(card.locator("form"));
  await card.getByRole("button", {name: "Set stock", exact: true}).click();
  await expect(card.getByLabel("Current quantity", {exact: true})).toHaveValue("1");
  await expect(card.getByLabel("Reason for change", {exact: true})).toHaveValue("");
  expect(await calls(page)).toEqual([]);
  expect(await page.evaluate(() => window.fixture.pantry.items[0])).toMatchObject({quantity: 1, revision: 1});
});

test("draft navigation: meal row removals and Cancel do not alter saved plans", async ({page}) => {
  await page.goto("/tests/fixtures/meals.html?actor=parent");
  const card = page.locator("family-meals-card"), before = await page.evaluate(() => structuredClone(window.fixture));
  await card.getByRole("button", {name: "New plan", exact: true}).click();
  const form = card.locator('[data-meals-form="new"]');
  await form.getByLabel("Plan title", {exact: true}).fill("Unsent menu");
  await form.getByRole("button", {name: "Add ingredient", exact: true}).click();
  await form.getByLabel("Ingredient name", {exact: true}).fill("Unsent ingredient");
  await form.getByRole("button", {name: "Remove ingredient", exact: true}).click();
  await expect(form.getByLabel("Ingredient name", {exact: true})).toHaveCount(0);
  await form.getByRole("button", {name: "Add meal", exact: true}).click();
  await expect(form.locator("[data-meals-entry]")).toHaveCount(2);
  await form.getByRole("button", {name: "Remove meal", exact: true}).last().click();
  await expect(form.locator("[data-meals-entry]")).toHaveCount(1);
  await expect(form.getByLabel("Plan title", {exact: true})).toHaveValue("Unsent menu");
  await cancel(form);
  for (const [title, action, type] of [["Private draft", "Publish plan", "publish"], ["Family menu", "Archive plan", "archive"]]) {
    await card.locator("[data-meal-plan]").filter({hasText: title}).getByRole("button", {name: action, exact: true}).click();
    await cancel(card.locator(`[data-meals-form="${type}"]`));
  }
  expect(await calls(page)).toEqual([]);
  expect(await page.evaluate(() => window.fixture)).toEqual(before);
  await card.getByRole("button", {name: "New plan", exact: true}).click();
  await expect(card.getByLabel("Plan title", {exact: true})).not.toHaveValue("Unsent menu");
});

test("draft navigation: recipe Back retains manual correction and Cancel clears candidate", async ({page}) => {
  await page.goto("/tests/fixtures/recipes.html");
  const card = page.locator("family-meals-card");
  await card.locator(".recipes-section > summary").click();
  await card.locator('[data-recipes-form="search"] button[type="submit"]').click();
  await card.locator('[data-recipe-slug="vegetable-soup"] button').click();
  let editor = card.locator('[data-recipes-form="edit"]');
  await editor.locator('[name="week_start"]').fill("2026-09-07");
  await editor.locator('[name="date"]').fill("2026-09-08");
  await editor.locator('[name="slot"]').selectOption("dinner");
  await editor.locator('[name="servings"]').fill("6");
  await editor.locator('[data-recipe-ingredient="1"] [name="unit"]').fill("kg");
  await editor.locator('[data-recipe-ingredient="1"] [name="quantity"]').fill("0.3");
  await editor.locator('[name="verified_1"]').check();
  await editor.locator('button[type="submit"]').click();
  await card.locator('[data-recipes-form="review"]').getByRole("button", {name: "Back", exact: true}).click();
  editor = card.locator('[data-recipes-form="edit"]');
  await expect(editor.locator('[name="slot"]')).toHaveValue("dinner");
  await expect(editor.locator('[name="servings"]')).toHaveValue("6");
  await expect(editor.locator('[data-recipe-ingredient="1"] [name="quantity"]')).toHaveValue("0.3");
  await expect(editor.locator('[name="verified_1"]')).toBeChecked();
  expect(await calls(page)).toEqual([]);
  await editor.locator('button[type="submit"]').click();
  await expect(card.locator('[data-recipes-form="review"] [name="reviewed"]')).not.toBeChecked();
  await cancel(card.locator('[data-recipes-form="review"]'));
  await expect(card.locator('[data-recipes-form="edit"], [data-recipes-form="review"]')).toHaveCount(0);
  expect(await calls(page)).toEqual([]);
  expect(await page.evaluate(() => window.fixture.pantry.meal_plans)).toEqual([]);
  expect(await page.evaluate(() => window.lookups.map(item => item.kind))).toEqual(["search", "get"]);
});

test("draft navigation: maintenance editor and named review Cancel never save equipment", async ({page}) => {
  await page.goto("/tests/fixtures/maintenance.html");
  const card = page.locator("family-maintenance-card"), before = await page.evaluate(() => structuredClone(window.fixture));
  await card.getByRole("button", {name: "Edit equipment", exact: true}).click();
  let editor = card.locator('[data-maintenance-form="asset_edit"]');
  await editor.locator('[name="name"]').fill("Unsent equipment rename");
  await cancel(editor);
  await card.getByRole("button", {name: "Edit equipment", exact: true}).click();
  editor = card.locator('[data-maintenance-form="asset_edit"]');
  await expect(editor.locator('[name="name"]')).toHaveValue(before.maintenance.assets[0].name);
  await editor.locator('[name="note"]').fill("Unsent maintenance review");
  await editor.locator('button[type="submit"]').click();
  const review = card.locator('[data-maintenance-form="review"]');
  await expect(review).toContainText("Unsent maintenance review");
  await cancel(review);
  await expect(review).toHaveCount(0);
  expect(await calls(page)).toEqual([]);
  expect(await page.evaluate(() => window.fixture)).toEqual(before);
});

test("draft navigation: poll create, vote and named review Cancel preserve ballots", async ({page}) => {
  await page.clock.setFixedTime(new Date("2026-10-01T12:00:00Z"));
  await page.goto("/tests/fixtures/polls.html?actor=parent");
  const card = page.locator("family-polls-card"), before = await page.evaluate(() => structuredClone(window.pollFixture));
  await card.getByRole("button", {name: "Create poll", exact: true}).click();
  let form = card.locator('[data-poll-form="create"]');
  await form.locator('[name="question"]').fill("Unsent poll question");
  await cancel(form);
  await card.getByRole("button", {name: "Create poll", exact: true}).click();
  form = card.locator('[data-poll-form="create"]');
  await expect(form.locator('[name="question"]')).toHaveValue("");
  await cancel(form);
  const poll = card.locator('[data-poll-id="PL000001"]');
  await poll.getByRole("button", {name: "Vote", exact: true}).click();
  form = card.locator('[data-poll-form="vote"]');
  await form.locator('[value="O1"]').check();
  await cancel(form);
  await poll.getByRole("button", {name: "Vote", exact: true}).click();
  form = card.locator('[data-poll-form="vote"]');
  await form.locator('[value="O1"]').check();
  await form.locator('button[type="submit"]').click();
  await cancel(card.locator('[data-poll-form="review"]'));
  expect(await calls(page)).toEqual([]);
  expect(await page.evaluate(() => window.pollFixture)).toEqual(before);
});

test("draft navigation: school homework editor and review Cancel clear only draft", async ({page}) => {
  await page.clock.setFixedTime(new Date("2026-09-07T07:00:00Z"));
  await page.goto("/tests/fixtures/school-work.html?actor=parent");
  const card = page.locator("family-school-card"), before = await page.evaluate(() => structuredClone(window.fixture.tasks));
  await card.getByRole("button", {name: "Add homework", exact: true}).click();
  let editor = card.locator('[data-school-work-editor="homework_create"]');
  await editor.locator('[name="title"]').fill("Unsent homework");
  await cancel(editor);
  await card.getByRole("button", {name: "Add homework", exact: true}).click();
  editor = card.locator('[data-school-work-editor="homework_create"]');
  await expect(editor.locator('[name="title"]')).toHaveValue("");
  await editor.locator('[name="title"]').fill("Reviewed but unsent homework");
  await editor.getByRole("button", {name: "Review", exact: true}).click();
  const review = card.locator('[data-school-work-review="homework_create"]');
  await expect(review).toContainText("Reviewed but unsent homework");
  await cancel(review);
  expect(await calls(page)).toEqual([]);
  expect(await page.evaluate(() => window.fixture.tasks)).toEqual(before);
});

test("draft navigation: fault photo empty submit is inert and Cancel sends no media request", async ({page}) => {
  await page.goto("/tests/fixtures/fault-photos.html");
  const card = page.locator("family-maintenance-card"), copy = FAULT_PHOTO_COPY.en;
  await card.getByRole("button", {name: copy.add, exact: true}).click();
  const form = card.locator('[data-fault-photo-form="upload"]');
  await submitForm(form);
  await expect(page).toHaveURL(/fault-photos.html$/);
  await expect(form).toBeVisible();
  await card.getByRole("button", {name: copy.cancel, exact: true}).click();
  await expect(form).toHaveCount(0);
  expect(await page.evaluate(() => ({calls: window.fixture.calls, http: window.fixture.http}))).toEqual({calls: [], http: []});
});

test("draft navigation: explicitly downloaded fault photo Hide revokes preview without changing evidence", async ({page}) => {
  await page.goto("/tests/fixtures/fault-photos.html");
  const card = page.locator("family-maintenance-card"), copy = FAULT_PHOTO_COPY.en;
  // Existing synthetic evidence is a starting condition, not a tested upload.
  const before = await page.evaluate(async () => {
    const fault = window.fixture.state.maintenance.faults[0];
    fault.photo_attachment = {id: "M0123456789abcdef0123456789abcdef", revision: 3, status: "attached", purpose: "maintenance_fault", mime_type: "image/png", size_bytes: 4};
    fault.can_upload_photo = false;
    fault.attachment_ids = [fault.photo_attachment.id];
    window.revokedPreviews = [];
    const revoke = URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL = value => {window.revokedPreviews.push(value); return revoke(value);};
    await window.fixture.card.refresh();
    return structuredClone(fault);
  });
  await card.getByRole("button", {name: copy.view, exact: true}).click();
  const image = card.locator(".fault-photo img");
  await expect.poll(() => image.evaluate(node => node.complete && node.naturalWidth > 0)).toBe(true);
  const preview = await image.getAttribute("src");
  await card.getByRole("button", {name: copy.hide, exact: true}).click();
  await expect(image).toHaveCount(0);
  expect(await page.evaluate(() => window.revokedPreviews)).toContain(preview);
  expect(await page.evaluate(() => window.fixture.calls)).toEqual([]);
  expect(await page.evaluate(() => window.fixture.http.map(item => item.method))).toEqual(["GET"]);
  expect(await page.evaluate(() => window.fixture.state.maintenance.faults[0])).toEqual(before);
});

test("draft navigation: digest alternate submit retries frozen request once and preview Cancel hides content", async ({page}) => {
  await page.goto("/tests/fixtures/digests.html?actor=parent");
  const card = page.locator("family-digests-card");
  await card.getByRole("button", {name: "Change preferences", exact: true}).click();
  await card.locator('[name="evening"]').check();
  await submitForm(card.locator(".digest-editor"));
  let review = card.locator(".digest-review");
  await expect(review).toBeVisible();
  expect(await calls(page)).toEqual([]);
  await review.locator('[name="confirmed"]').check();
  await page.evaluate(() => window.failMode = "before");
  await submitForm(review);
  await expect(review.getByRole("button", {name: "Retry exact request", exact: true})).toBeVisible();
  await submitForm(review);
  await expect(review).toHaveCount(0);
  const written = await calls(page);
  expect(written).toHaveLength(2);
  expect(written[1]).toEqual(written[0]);
  expect(written[0]).toMatchObject({action: "digests.access_set", payload: {morning: true, evening: true, weekly: false}});
  await card.getByRole("button", {name: "Change preferences", exact: true}).click();
  await card.locator('[name="weekly"]').check();
  await cancel(card.locator(".digest-editor"));
  await card.getByRole("button", {name: "Build private preview", exact: true}).click();
  await expect(card.locator(".digest-preview-section")).toHaveCount(5);
  await cancel(card.locator(".digest-preview"));
  await expect(card.locator(".digest-preview-section")).toHaveCount(0);
  expect((await calls(page)).filter(item => item.type === "family_assistant/execute")).toEqual(written);
});

test("draft navigation: presence Cancel refuses consent and alternate submit preserves exact retry", async ({page}) => {
  await page.goto("/tests/fixtures/presence.html?actor=parent");
  const card = page.locator("family-presence-card"), own = card.locator(".presence-self");
  await own.getByRole("button", {name: "Enable sharing", exact: true}).click();
  await cancel(card.locator(".presence-review"));
  expect(await calls(page)).toEqual([]);
  await own.getByRole("button", {name: "Enable sharing", exact: true}).click();
  const review = card.locator(".presence-review");
  await review.locator('[name="confirmed"]').check();
  await page.evaluate(() => window.failMode = "after");
  await submitForm(review);
  await expect(review.getByRole("button", {name: "Retry exact request", exact: true})).toBeVisible();
  await submitForm(review);
  await expect(review).toHaveCount(0);
  const sent = await calls(page);
  expect(sent).toHaveLength(2);
  expect(sent[1]).toEqual(sent[0]);
  expect(sent[0]).toMatchObject({action: "presence.access_set", payload: {member: "parent-1", enabled: true}});
});

test("draft navigation: return-home notification Cancel resets wait and alternate submit writes once", async ({page}) => {
  await page.goto("/tests/fixtures/presence-notifications.html");
  const card = page.locator("family-presence-card"), section = card.locator(".presence-notifications");
  const child = section.locator('[data-notification-member="child"]');
  await child.getByRole("button", {name: "Configure & enable", exact: true}).click();
  await section.getByLabel("Maximum wait time (minutes)", {exact: false}).fill("45");
  await cancel(section.locator("form"));
  expect(await calls(page)).toEqual([]);
  await child.getByRole("button", {name: "Configure & enable", exact: true}).click();
  await expect(section.getByLabel("Maximum wait time (minutes)", {exact: false})).toHaveValue("720");
  await section.getByLabel("Maximum wait time (minutes)", {exact: false}).fill("45");
  await section.locator('[name="confirmed"]').check();
  await submitForm(section.locator("form"));
  await expect(section.locator("form")).toHaveCount(0);
  const sent = await calls(page);
  expect(sent).toHaveLength(1);
  expect(sent[0]).toMatchObject({action: "presence.guardian_notification_access_set", payload: {member: "child", max_wait_minutes: 45, enabled: true}});
  expect(await page.evaluate(() => window.fixture.presence.notifications.managed[0])).toMatchObject({preference_revision: 1, max_wait_minutes: 45, enabled: true});
});

test("draft navigation: school reminder form submit cannot bypass explicit save and Cancel clears consent", async ({page}) => {
  await page.goto("/tests/fixtures/school-reminders.html");
  const card = page.locator("family-school-card"), row = card.locator('[data-school-reminder-member="child-1"]');
  await row.getByRole("button", {name: "Enable for me", exact: true}).click();
  const review = card.locator(".school-reminder-review");
  await review.locator('[name="confirmed"]').check();
  await submitForm(review);
  await expect(review).toBeVisible();
  expect(await calls(page)).toEqual([]);
  await cancel(review);
  await row.getByRole("button", {name: "Enable for me", exact: true}).click();
  await expect(review.locator('[name="confirmed"]')).not.toBeChecked();
  expect(await calls(page)).toEqual([]);
});
