import {test,expect} from "./control-audit.js";
import {SETTLEMENT_COPY} from "../../custom_components/family_assistant/frontend/task-settlements.js";
import {TASK_ITEM_COPY} from "../../custom_components/family_assistant/frontend/task-items.js";
const add = {en:"Add",ru:"Добавить",uk:"Додати"};
const form = page => page.locator("form[data-task-create]");
const calls = page => page.evaluate(() => window.calls);
async function open(page, language="en", suffix="") {
  await page.goto(`/tests/fixtures/task-settlements.html?lang=${language}${suffix}`);
  await expect(page.getByRole("button",{name:add[language],exact:true})).toBeVisible();
}
async function create(page, language="en") {
  await page.getByRole("button",{name:add[language],exact:true}).click();
  const editor = form(page);
  await editor.locator('[name="title"]').fill("Synthetic settlement task");
  await editor.locator('[name="assignee"]').selectOption("child");
  await editor.locator('[name="due_at"]').fill("2030-09-06T19:00");
  await editor.locator("details > summary").click();
  return editor;
}
for (const language of ["en","ru","uk"]) {
  test(`settlement ${language}: separate consent creates, edits and disables actual policy`, async ({page}) => {
    await page.setViewportSize({width:390,height:844});
    await open(page,language);
    const editor = await create(page,language), copy = SETTLEMENT_COPY[language];
    const daily = editor.getByLabel(copy.daily_rollover,{exact:true});
    await expect(daily).not.toBeChecked();
    await expect(editor.getByLabel(copy.repeat_penalty,{exact:true})).toBeDisabled();
    await daily.check();
    await expect(editor.getByLabel(copy.repeat_penalty,{exact:true})).not.toBeChecked();
    await editor.getByLabel(copy.repeat_penalty,{exact:true}).check();
    await editor.getByLabel(copy.same_day_correction,{exact:true}).check();
    await editor.getByLabel(copy.settle_time,{exact:true}).fill("21:15");
    await editor.locator('button[type="submit"]').click();
    await expect(editor).toHaveCount(0);
    expect((await calls(page))[0].payload).toMatchObject({missed_actor_revision:1,missed_policy:{daily_rollover:true,settle_time:"21:15",repeat_penalty:true,same_day_correction:true}});
    const item = page.locator(".body > ul.list > li.item").first();
    await item.getByRole("button",{name:TASK_ITEM_COPY[language].action_edit,exact:true}).click();
    const edit = item.locator("form");
    await edit.locator("details > summary").click();
    await expect(edit.getByLabel(copy.settle_time,{exact:true})).toHaveValue("21:15");
    await expect(edit.getByLabel(copy.repeat_penalty,{exact:true})).toBeChecked();
    await edit.getByLabel(copy.daily_rollover,{exact:true}).uncheck();
    await edit.locator('button[type="submit"]').click();
    await expect(edit).toHaveCount(0);
    expect((await calls(page)).at(-1).payload.missed_policy).toEqual({daily_rollover:false,settle_time:"21:15",repeat_penalty:false,same_day_correction:false});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
test("omission remains omission on default create and untouched existing edit",async({page}) => {
  await open(page);
  let editor = await create(page);
  await editor.locator('button[type="submit"]').click();
  expect((await calls(page))[0].payload).not.toHaveProperty("missed_policy");
  await page.locator(".body > ul.list > li.item").first().getByRole("button",{name:TASK_ITEM_COPY.en.action_edit,exact:true}).click();
  editor = page.locator(".body > ul.list > li.item form");
  await editor.locator('button[type="submit"]').click();
  expect((await calls(page)).at(-1).payload).not.toHaveProperty("missed_policy");
});
test("create failed-save retry freezes policy and operation",async({page}) => {
  await open(page); let editor = await create(page);
  await editor.locator('[name="missed_daily_rollover"]').check();
  await editor.locator('[name="missed_repeat_penalty"]').check();
  await page.evaluate(() => {window.failCommand=true;});
  await editor.locator('button[type="submit"]').click();
  await expect(editor.locator('[name="missed_daily_rollover"]')).toBeDisabled();
  const first = (await calls(page))[0];
  await page.evaluate(() => {window.failCommand=false;});
  editor = form(page); await editor.locator('button[type="submit"]').click();
  expect((await calls(page)).at(-1)).toEqual(first);
});
test("child cannot configure; personal, adult and multi-person creation cannot activate policy",async({page}) => {
  await open(page,"en","&actor=child"); await page.getByRole("button",{name:"Add",exact:true}).click();
  await expect(form(page).locator("[data-task-settlement]")).toHaveCount(0);
  await open(page); const editor = await create(page);
  await editor.locator('[name="assignee"]').selectOption("adult");
  await expect(editor.locator('[name="missed_daily_rollover"]')).toBeDisabled();
  await editor.locator('[name="assignee"]').selectOption("child");
  await editor.locator('[name="missed_daily_rollover"]').check();
  await editor.locator('[name="personal"]').check();
  await expect(editor.locator('[name="missed_daily_rollover"]')).toBeDisabled();
  await editor.locator('[name="personal"]').uncheck();
  await editor.locator('[name="multi"]').check();
  await expect(editor.locator('[name="missed_daily_rollover"]')).toBeDisabled();
  await editor.locator('[name="assignee_multi"][value="child"]').check();
  await editor.locator('[name="assignee_multi"][value="sibling"]').check();
  await editor.locator('button[type="submit"]').click();
  await expect(page.locator(".task-multi-review-preview")).toBeVisible();
  expect(await calls(page)).toHaveLength(0);
  expect(await page.evaluate(() => window.card._taskCreateDraft.payload)).toBeFalsy();
});

test("valid cutoff required; editor failed-save retains frozen reviewed policy",async({page}) => {
  await open(page,"en","&seed=1&policy=1");
  const item = page.locator(".body > ul.list > li.item").first();
  await item.getByRole("button",{name:TASK_ITEM_COPY.en.action_edit,exact:true}).click();
  const editor = item.locator("form");
  await editor.locator("details > summary").click();
  await editor.locator('[name="missed_settle_time"]').fill("");
  await editor.locator('button[type="submit"]').click();
  expect(await calls(page)).toHaveLength(0);
  await editor.locator('[name="missed_settle_time"]').fill("23:59");
  await editor.locator('[name="missed_same_day_correction"]').check();
  await page.evaluate(() => {window.failCommand=true;});
  await editor.locator('button[type="submit"]').click();
  await expect(editor.locator('[name="missed_daily_rollover"]')).toBeDisabled();
  const first = (await calls(page))[0];
  expect(first.payload.missed_policy.settle_time).toBe("23:59");
  await page.evaluate(() => {window.failCommand=false;});
  await editor.locator('button[type="submit"]').click();
  expect((await calls(page)).at(-1)).toEqual(first);
});

test("exact correction button freezes task, settlement, Court and actor revisions on retry",async({page}) => {
  await open(page,"en","&seed=1&policy=1&correction=1");
  await page.getByText("Archived & Completed Tasks",{exact:true}).click();
  const button = page.getByRole("button",{name:SETTLEMENT_COPY.en.corrected,exact:true});
  await page.evaluate(() => {window.failCommand=true;});
  await button.click();
  await expect(button).toBeEnabled();
  const first = (await calls(page))[0];
  expect(first.action).toBe("tasks.correct_miss");
  expect(first.payload).toMatchObject({id:"T000001",revision:1,actor_revision:1,court_revision:2,settlement_id:"T000001:missed:1:2030-09-06"});
  await page.evaluate(() => {window.failCommand=false;});
  await button.click();
  expect((await calls(page)).at(-1)).toEqual(first);
  await expect(button).toHaveCount(0);
});

for (const language of ["en","ru","uk"]) test(`capacity ${language}: truthful non-destructive pause is visible without opening editor`,async({page}) => {
  await open(page,language,"&seed=1&policy=1&capacity=1");
  await expect(page.getByText(SETTLEMENT_COPY[language].settlement_capacity,{exact:true})).toBeVisible();
  expect(await calls(page)).toHaveLength(0);
});
for (const scope of ["private","personal"]) test(`unsupported ${scope} edit has no settlement controls`,async({page}) => {
  await open(page,"en",`&seed=1&scope=${scope}`);
  await page.locator(".body > ul.list > li.item").first().getByRole("button",{name:TASK_ITEM_COPY.en.action_edit,exact:true}).click();
  await expect(page.locator("[data-task-settlement]")).toHaveCount(0);
});
