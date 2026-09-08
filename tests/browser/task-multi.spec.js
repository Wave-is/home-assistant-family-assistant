import {test,expect} from "@playwright/test";
import {TASK_FORM_COPY} from "../../custom_components/family_assistant/frontend/task-form.js";

async function open(page,lang="en",role="owner") {
  await page.goto(`/tests/fixtures/task-multi.html?lang=${lang}&role=${role}`);
  await page.getByRole("button",{name:{en:"Add",ru:"Добавить",uk:"Додати"}[lang],exact:true}).click();
  const form=page.locator("form[data-task-create]");
  await form.locator('[name="title"]').fill("Water each room's plants");
  return {form,copy:TASK_FORM_COPY[lang]};
}

async function review(page,lang="en",wall="2026-10-20T17:00",fold=null) {
  const {form,copy}=await open(page,lang);
  await form.locator('[name="multi"]').check();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await expect(form.locator('[name="assignee_multi"][value="guest"]')).toHaveCount(0);
  await form.locator('[name="assignee_multi"][value="first"]').check();
  await form.locator('[name="assignee_multi"][value="second"]').check();
  await form.locator('[name="due_at"]').fill(wall);
  if(fold!==null)await form.locator('[name="due_fold"]').selectOption(fold);
  await form.locator('[name="checklist"]').fill("Check soil\nWater");
  await form.locator('button[type="submit"]').click();
  await expect(form.locator(".task-multi-review-preview")).toBeVisible();
  return {form,copy};
}

for(const lang of ["en","ru","uk"])test(`multi assignment ${lang}: mobile review, separate records and household-zone deadline`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const {form,copy}=await review(page,lang);
  await expect(form.locator(".task-multi-review-preview")).toContainText("Child 1");
  await expect(form.locator(".task-multi-review-preview")).toContainText("Child 2");
  await expect(form.getByRole("button",{name:copy.applyBatch,exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await form.locator('[name="confirm_batch"]').check();
  await page.screenshot({path:`test-results/task-multi-review-${lang}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await form.getByRole("button",{name:copy.applyBatch,exact:true}).click();
  await expect(form).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(1);expect(calls[0].action).toBe("batch");
  expect(calls[0].payload.commands).toHaveLength(2);
  for(const [i,member] of ["first","second"].entries())expect(calls[0].payload.commands[i]).toEqual({action:"tasks.create",payload:{
    title:"Water each room's plants",assignee:member,assignee_revision:1,
    due_at:"2026-10-20T15:00:00.000Z",checklist:["Check soil","Water"],report_type:"text",reminder_minutes:60,grace_minutes:30,penalty:0,
  }});
  const tasks=await page.evaluate(()=>window.fixture.tasks);
  expect(tasks.map(t=>t.assignee)).toEqual(["first","second"]);
  expect(new Set(tasks.map(t=>t.id)).size).toBe(2);
});

test("uncertain multi-create retries its own exact ID after another card command",async({page})=>{
  const {form}=await review(page);
  await form.locator('[name="confirm_batch"]').check();
  await page.evaluate(()=>window.loseReplyOnce=true);
  await form.locator('button[type="submit"]').click();
  await expect(form.locator('button[type="submit"]')).toBeEnabled();
  const original=await page.evaluate(()=>window.calls[0]);
  await page.evaluate(()=>window.card.command("tasks.cancel",{id:window.fixture.tasks[0].id,revision:1}));
  await form.locator('button[type="submit"]').click();
  expect(await page.evaluate(()=>window.calls.at(-1))).toEqual(original);
  expect(await page.evaluate(()=>window.fixture.tasks)).toHaveLength(2);
});

test("changed member review cannot submit through detached confirmation",async({page})=>{
  const {form}=await review(page);
  await form.locator('[name="confirm_batch"]').check();
  await page.evaluate(()=>{
    window.oldMultiForm=window.card.shadowRoot.querySelector("form[data-task-create]");
    window.fixture.members.find(m=>m.id==="second").revision++;
    return window.card.refresh();
  });
  await expect(form.locator(".task-multi-review-preview")).toHaveCount(0);
  await page.evaluate(()=>window.oldMultiForm.dispatchEvent(new Event("submit",{cancelable:true,bubbles:true})));
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("rerender after actor epoch change clears the old private multi draft",async({page})=>{
  const {form}=await review(page);
  await form.locator('[name="confirm_batch"]').check();
  await page.evaluate(()=>{
    window.card._data.members.find(m=>m.id==="owner").revision++;
    window.card._data.actor_revision++;
    window.card.render();
  });
  await expect(page.locator(".task-multi-review-preview")).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await expect(page.locator('form[data-task-create] [name="title"]')).not.toHaveValue("Water each room's plants");
});

test("child has only self assignment and no multi selector",async({page})=>{
  const {form}=await open(page,"uk","child");
  await expect(form.locator('[name="multi"]')).toHaveCount(0);
  await expect(form.locator('select[name="assignee"] option')).toHaveCount(1);
  await expect(form.locator('select[name="assignee"]')).toHaveValue("first");
});

for(const [name,wall,fold,expected]of[
  ["ordinary deadline","2026-10-20T17:00",null,"2026-10-20T15:00:00.000Z"],
  ["DST second occurrence","2026-10-25T02:30","1","2026-10-25T01:30:00.000Z"],
])test(`review back retains ${name}`,async({page})=>{
  const {form,copy}=await review(page,"ru",wall,fold);
  await form.getByRole("button",{name:copy.back,exact:true}).click();
  await expect(form.locator('[name="due_at"]')).toHaveValue(wall);
  if(fold!==null)await expect(form.locator('[name="due_fold"]')).toHaveValue(fold);
  await form.locator('button[type="submit"]').click();
  await form.locator('[name="confirm_batch"]').check();
  await form.locator('button[type="submit"]').click();
  expect(await page.evaluate(()=>window.calls[0].payload.commands[0].payload.due_at)).toBe(expected);
});
