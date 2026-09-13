import { test, expect } from "./control-audit.js";
import { TASK_BATCH_COPY } from "../../custom_components/family_assistant/frontend/task-batch-copy.js";

async function select(page, lang="en", action="tasks.complete", ids=["T000001","T000002"]) {
  const copy=TASK_BATCH_COPY[lang];
  await page.goto(`/tests/fixtures/task-batch.html?lang=${lang}`);
  const panel=page.locator(".task-batch");
  await panel.locator("summary").click();
  await panel.getByRole("button",{name:copy.startBatch,exact:true}).click();
  await panel.locator('select[name="batch_action"]').selectOption(action);
  await expect(panel.locator('input[name="task_select"][value="T000029"]')).toHaveCount(0);
  await expect(panel.locator('input[name="task_select"][value="T000030"]')).toHaveCount(0);
  for(const id of ids)await panel.locator(`input[name="task_select"][value="${id}"]`).check();
  await panel.getByRole("button",{name:copy.reviewBatch,exact:true}).click();
  return {panel,copy};
}

for(const lang of ["en","ru","uk"])test(`task batch ${lang}: explicit review and one atomic payload on mobile`,async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const {panel,copy}=await select(page,lang);
  await expect(panel.locator(".task-batch-review")).toContainText("Water plants");
  await expect(panel.locator(".task-batch-review")).toContainText("Tidy desk");
  await expect(panel.getByRole("button",{name:copy.applyBatch,exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await panel.getByRole("checkbox",{name:copy.confirmLabel,exact:true}).check();
  await page.screenshot({path:`test-results/task-batch-review-${lang}.png`,fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(await panel.locator(".task-batch-preview").evaluate(el=>el.scrollWidth<=el.clientWidth)).toBe(true);
  await panel.getByRole("button",{name:copy.applyBatch,exact:true}).click();
  await expect(panel.locator(".task-batch-review")).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("batch");
  expect(calls[0].payload).toEqual({commands:[
    {action:"tasks.complete",payload:{id:"T000001",revision:1}},
    {action:"tasks.complete",payload:{id:"T000002",revision:1}},
  ]});
});

test("lost reply preserves the reviewed operation after another card command",async({page})=>{
  const {panel,copy}=await select(page);
  await panel.getByRole("checkbox",{name:copy.confirmLabel,exact:true}).check();
  await page.evaluate(()=>window.loseReplyOnce=true);
  await panel.getByRole("button",{name:copy.applyBatch,exact:true}).click();
  await expect(panel.getByRole("button",{name:copy.retry,exact:true})).toBeVisible();
  const first=await page.evaluate(()=>window.calls[0]);
  await page.evaluate(()=>window.card.command("tasks.cancel",{id:"T000007",revision:1}));
  await panel.getByRole("button",{name:copy.retry,exact:true}).click();
  await expect(panel.locator(".task-batch-review")).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(3);expect(calls[2]).toEqual(first);
  expect(await page.evaluate(()=>window.fixture.tasks.find(t=>t.id==="T000001").revision)).toBe(2);
});

for(const change of ["actor_revision","assignee_revision","assignee_changed"])test(`uncertain review is revoked by ${change}`,async({page})=>{
  const {panel,copy}=await select(page);
  await panel.getByRole("checkbox",{name:copy.confirmLabel,exact:true}).check();
  await page.evaluate(()=>window.failCommand=true);
  await panel.getByRole("button",{name:copy.applyBatch,exact:true}).click();
  await expect(panel.getByRole("button",{name:copy.retry,exact:true})).toBeVisible();
  await page.evaluate(async kind=>{
    window.oldBatchRetry=window.card.shadowRoot.querySelector(".task-batch-review button");
    if(kind==="actor_revision")window.fixture.members[0].revision++;
    if(kind==="assignee_revision")window.fixture.members[1].revision++;
    if(kind==="assignee_changed")window.fixture.tasks[0].assignee="owner";
    await window.card.refresh();
  },change);
  await expect(panel.locator(".task-batch-review")).toHaveCount(0);
  await page.evaluate(()=>window.oldBatchRetry.click());
  expect(await page.evaluate(()=>window.calls)).toHaveLength(1);
  expect(await page.evaluate(()=>window.card._taskBatchDraft)).toBeNull();
});

test("archive selection excludes active, private and specialized tasks; child has no panel",async({page})=>{
  const {panel,copy}=await select(page,"uk","tasks.archive",["T000003","T000004"]);
  await expect(panel.locator(".task-batch-preview article")).toHaveCount(2);
  await panel.getByRole("checkbox",{name:copy.confirmLabel,exact:true}).check();
  await panel.getByRole("button",{name:copy.applyBatch,exact:true}).click();
  expect(await page.evaluate(()=>window.fixture.tasks.filter(t=>t.status==="archived").map(t=>t.id))).toEqual(["T000003","T000004"]);
  await page.goto("/tests/fixtures/task-batch.html?role=child");
  await expect(page.locator("family-tasks-card")).toBeVisible();
  await expect(page.locator(".task-batch")).toHaveCount(0);
});

test("stale first review makes no request and reports reselection",async({page})=>{
  const {panel,copy}=await select(page);
  await panel.getByRole("checkbox",{name:copy.confirmLabel,exact:true}).check();
  await page.evaluate(async()=>{
    window.oldBatchConfirm=window.card.shadowRoot.querySelector(".task-batch-review button");
    window.fixture.tasks[0].revision++;
    await window.card.refresh();
  });
  await expect(panel.locator(".task-batch-review")).toHaveCount(0);
  await expect(panel.getByRole("alert")).toHaveText(copy.staleError);
  await page.evaluate(()=>window.oldBatchConfirm.click());
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
});
