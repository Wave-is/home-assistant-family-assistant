import {test,expect} from "./control-audit.js";

const root=page=>page.locator("family-routines-card");
const snapshot=page=>page.evaluate(()=>structuredClone(window.fixture));
const calls=page=>page.evaluate(()=>window.calls);
async function openDraft(page,kind){
  const card=root(page);
  if(kind==="modes")await card.locator("summary").filter({hasText:"Household routine modes"}).click();
  await card.getByRole("button",{name:{modes:"Update modes",start:"Start routine",override:"Parent override",cancel:"Cancel run"}[kind],exact:true}).click();
  const form=card.locator("form.editor");await expect(form).toHaveCount(1);return form;
}
async function exactRetry(page,action,payload){
  const attempts=await calls(page);expect(attempts).toHaveLength(2);expect(attempts[1]).toEqual(attempts[0]);
  expect(attempts[0]).toMatchObject({type:"family_assistant/execute",entry_id:"synthetic",action,payload});
  expect(attempts[0].payload).toEqual(payload);expect(attempts[0].operation_id).toMatch(/^[0-9a-f-]{36}$/);
}

test("routine modes enforce Normal exclusivity, local Cancel and exact failed-save retry",async({page})=>{
  await page.goto("/tests/fixtures/routines.html");const card=root(page),before=await snapshot(page);
  let form=await openDraft(page,"modes");await form.getByLabel("Vacation",{exact:true}).check();
  await form.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await snapshot(page)).toEqual(before);expect(await calls(page)).toEqual([]);
  form=await openDraft(page,"modes");await form.getByLabel("Holidays",{exact:true}).check();await form.getByLabel("Guests",{exact:true}).check();
  await expect(form.getByLabel("Normal (exclusive)",{exact:true})).not.toBeChecked();
  await form.getByLabel("Normal (exclusive)",{exact:true}).check();
  await expect(form.getByLabel("Holidays",{exact:true})).not.toBeChecked();await expect(form.getByLabel("Guests",{exact:true})).not.toBeChecked();
  await form.getByLabel("Normal (exclusive)",{exact:true}).click();await expect(form.getByLabel("Normal (exclusive)",{exact:true})).toBeChecked();
  await form.getByLabel("Holidays",{exact:true}).check();await form.getByLabel("Illness",{exact:true}).check();
  await page.evaluate(()=>window.failCommand=true);await form.getByRole("button",{name:"Save",exact:true}).click();
  await expect(form.getByRole("button",{name:"Retry",exact:true})).toBeVisible();await expect(form.getByLabel("Holidays",{exact:true})).toBeDisabled();
  expect(await snapshot(page)).toEqual(before);
  await page.evaluate(()=>window.failCommand=false);await form.getByRole("button",{name:"Retry",exact:true}).click();
  await expect(form).toHaveCount(0);await exactRetry(page,"routines.modes",{modes:["holidays","ill"],revision:0});
  before.routines.config.modes=["holidays","ill"];before.routines.config.revision++;before.revision++;
  expect(await snapshot(page)).toEqual(before);
  await card.locator("summary").filter({hasText:"Household routine modes"}).click();await expect(card.getByRole("button",{name:"Update modes",exact:true})).toBeVisible();
});

test("routine parent start preserves selected member and accepted-but-lost retry creates one run",async({page})=>{
  await page.goto("/tests/fixtures/routines.html?multi");const before=await snapshot(page);
  let form=await openDraft(page,"start");await form.getByRole("combobox",{name:"Assignee for this run",exact:true}).selectOption("child");
  await form.getByRole("button",{name:"Cancel",exact:true}).click();expect(await snapshot(page)).toEqual(before);expect(await calls(page)).toEqual([]);
  form=await openDraft(page,"start");await form.getByRole("combobox",{name:"Assignee for this run",exact:true}).selectOption("child");
  await page.evaluate(()=>window.commitThenLose=true);await form.getByRole("button",{name:"Start",exact:true}).click();
  await expect(form.getByRole("button",{name:"Retry",exact:true})).toBeVisible();await expect(form.getByRole("combobox",{name:"Assignee for this run",exact:true})).toBeDisabled();
  const accepted=await snapshot(page);expect(accepted.routines.runs).toHaveLength(1);expect(accepted.routines.runs[0]).toMatchObject({member:"child",template_id:"U000001",template_revision:1,revision:2,status:"active"});
  await form.getByRole("button",{name:"Retry",exact:true}).click();await expect(form).toHaveCount(0);
  await exactRetry(page,"routines.start",{id:"U000001",revision:1,member:"child"});expect(await snapshot(page)).toEqual(accepted);
  expect(accepted.routines.templates).toEqual(before.routines.templates);expect(accepted.routines.config).toEqual(before.routines.config);
  await expect(root(page).getByRole("button",{name:"Parent override",exact:true})).toHaveCount(1);
});

test("routine child start is self-only and does not duplicate the existing active run",async({page})=>{
  await page.goto("/tests/fixtures/routines.html?child&multi");const card=root(page),before=await snapshot(page);
  for(const name of ["Update modes","Parent override","Cancel run"])await expect(card.getByRole("button",{name,exact:true})).toHaveCount(0);
  const form=await openDraft(page,"start");await expect(form.locator("select")).toHaveCount(0);await expect(form).toContainText("Assignee for this run: Child 1");
  await form.getByRole("button",{name:"Start",exact:true}).click();await expect(form).toHaveCount(0);
  expect((await calls(page)).map(call=>({action:call.action,payload:call.payload}))).toEqual([{action:"routines.start",payload:{id:"U000001",revision:1,member:"child"}}]);
  const after=await snapshot(page);expect(after.routines).toEqual(before.routines);expect(after.revision).toBe(before.revision+1);
});

for(const outcome of ["completed","skipped"])test(`routine parent override ${outcome} requires a reason and advances exactly once after retry`,async({page})=>{
  await page.goto("/tests/fixtures/routines.html?run");const card=root(page),before=await snapshot(page);
  let form=await openDraft(page,"override");await form.getByLabel("Reason",{exact:true}).fill("Draft only");
  await form.getByRole("button",{name:"Cancel",exact:true}).click();expect(await snapshot(page)).toEqual(before);expect(await calls(page)).toEqual([]);
  form=await openDraft(page,"override");await form.getByLabel("Reason",{exact:true}).fill("   ");await form.getByRole("button",{name:"Save",exact:true}).click();
  await expect(card.getByRole("alert")).toContainText("Reason is required");expect(await calls(page)).toEqual([]);
  await form.getByRole("combobox",{name:"Parent override",exact:true}).selectOption(outcome);await form.getByLabel("Reason",{exact:true}).fill("  Synthetic parent review  ");
  await page.evaluate(()=>window.failCommand=true);await form.getByRole("button",{name:"Save",exact:true}).click();
  await expect(form.getByRole("button",{name:"Retry",exact:true})).toBeVisible();expect(await snapshot(page)).toEqual(before);
  await expect(form.getByLabel("Reason",{exact:true})).toBeDisabled();await page.evaluate(()=>window.failCommand=false);await form.getByRole("button",{name:"Retry",exact:true}).click();
  await expect(form).toHaveCount(0);await exactRetry(page,"routines.override",{id:"J000001",revision:2,step:0,outcome,reason:"Synthetic parent review"});
  const after=await snapshot(page),run=after.routines.runs[0];expect(run.revision).toBe(4);expect(run.status).toBe("active");
  expect(run.steps.map(step=>step.status)).toEqual([outcome,"active"]);expect(run.steps[0]).not.toHaveProperty("nonce");expect(run.steps[1].nonce).toBe("synthetic-fresh-second");
  expect(run.history.slice(-2).map(item=>({action:item.action,reason:item.reason,step:item.step}))).toEqual([{action:`step_${outcome}`,reason:"Synthetic parent review",step:0},{action:"step_activated",reason:"",step:1}]);
  expect(after.routines.templates).toEqual(before.routines.templates);expect(after.routines.config).toEqual(before.routines.config);
  await expect(card.getByRole("button",{name:"Parent override",exact:true})).toHaveCount(1);
});

test("routine run Cancel is local until reasoned review and failed cancellation retries one revision",async({page})=>{
  await page.goto("/tests/fixtures/routines.html?run");const card=root(page),before=await snapshot(page);
  let form=await openDraft(page,"cancel");await form.getByLabel("Reason",{exact:true}).fill("Unsubmitted reason");
  await form.getByRole("button",{name:"Cancel",exact:true}).click();expect(await snapshot(page)).toEqual(before);expect(await calls(page)).toEqual([]);
  form=await openDraft(page,"cancel");await form.getByLabel("Reason",{exact:true}).fill(" ");await form.getByRole("button",{name:"Cancel run",exact:true}).click();
  await expect(card.getByRole("alert")).toContainText("Reason is required");expect(await calls(page)).toEqual([]);
  await form.getByLabel("Reason",{exact:true}).fill("  Synthetic schedule change  ");await page.evaluate(()=>window.failCommand=true);
  await form.getByRole("button",{name:"Cancel run",exact:true}).click();await expect(form.getByRole("button",{name:"Retry",exact:true})).toBeVisible();expect(await snapshot(page)).toEqual(before);
  await page.evaluate(()=>window.failCommand=false);await form.getByRole("button",{name:"Retry",exact:true}).click();await expect(form).toHaveCount(0);
  await exactRetry(page,"routines.cancel",{id:"J000001",revision:2,reason:"Synthetic schedule change"});
  const after=await snapshot(page),run=after.routines.runs[0];expect(run).toMatchObject({status:"cancelled",cancellation_cause:"manual",revision:3});
  expect(run.history.at(-1)).toMatchObject({action:"cancelled",reason:"Synthetic schedule change"});expect(run.steps.every(step=>!step.nonce)).toBe(true);
  expect(after.routines.templates).toEqual(before.routines.templates);expect(after.routines.config).toEqual(before.routines.config);
  await expect(card.getByRole("button",{name:"Cancel run",exact:true})).toHaveCount(0);
});

for(const kind of ["modes","start","override","cancel"])for(const drift of ["role","revision"])test(`routine ${kind} detached submit cannot bypass fresh ${drift} guard`,async({page})=>{
  await page.goto("/tests/fixtures/routines.html?run&multi");const form=await openDraft(page,kind);
  if(["override","cancel"].includes(kind))await form.getByLabel("Reason",{exact:true}).fill("Synthetic stale review");
  await form.evaluate(node=>window.detachedRoutineForm=node);
  await page.evaluate(async({kind,drift})=>{
    if(drift==="role"){window.fixture.role="child";const actor=window.fixture.members.find(member=>member.id===window.fixture.actor);actor.role="child";actor.revision++;}
    else if(kind==="modes")window.fixture.routines.config.revision++;
    else if(kind==="start")window.fixture.routines.templates[0].revision++;
    else window.fixture.routines.runs[0].revision++;
    await window.card.refresh();
  },{kind,drift});
  const before=await snapshot(page);await expect(form).toHaveCount(0);
  await page.evaluate(()=>window.detachedRoutineForm.requestSubmit());
  expect(await calls(page)).toEqual([]);expect(await snapshot(page)).toEqual(before);
  expect(await page.evaluate(()=>window.card._routineDraft)).toBeNull();
});
