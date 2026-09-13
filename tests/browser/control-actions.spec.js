import {test,expect} from "./control-audit.js";
import {PANEL_MODULES} from "../../custom_components/family_assistant/frontend/panel-copy.js";

// Each scenario below asserts its named action's payload/readback or deliberate
// refusal. Synthetic starting states do not count as UI actions or HA acceptance.
for(const [id,,titles] of PANEL_MODULES)test(`control sweep: panel ${id} configuration toggle preserves other modules`,async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=page.locator("family-assistant-panel");
  await panel.locator(".nav-tabs-bar").getByRole("button",{name:/Capabilities/}).click();
  await panel.locator(".panel-module-card").filter({has:page.getByRole("heading",{name:new RegExp(titles[0])})}).getByRole("button",{name:"Configure",exact:true}).click();
  const before=await page.evaluate(()=>structuredClone(window.fixture.data.view.settings.modules));
  const toggle=panel.locator(".panel-toggle input");await toggle.setChecked(!before.includes(id));
  await expect(panel).toContainText("Saved and verified");
  const changed=before.includes(id)?before.filter(value=>value!==id):[...before,id];
  const call=await page.evaluate(()=>window.fixture.calls.find(item=>item.action==="settings.patch"));
  expect(call.payload).toEqual({revision:1,changes:{modules:changed.sort()}});
  expect(await page.evaluate(()=>window.fixture.data.view.settings.modules)).toEqual(changed.sort());
  await expect(toggle).toBeChecked({checked:!before.includes(id)});
});

test("control sweep: family settings frozen retry, native setup discard refusal and navigation",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=page.locator("family-assistant-panel");
  await panel.locator(".nav-tabs-bar").getByRole("button",{name:/Advanced/}).click();
  await panel.locator('[name="name"]').fill("Synthetic revised family");
  await panel.locator('[name="timezone"]').fill("UTC");
  const native=panel.locator('a[href="/config/integrations/integration/family_assistant"]');
  page.once("dialog",dialog=>dialog.dismiss());await native.click();await expect(page).toHaveURL(/panel.html/);
  expect(await page.evaluate(()=>window.fixture.calls.filter(item=>item.type==="family_assistant/execute"))).toEqual([]);
  await page.evaluate(()=>window.fixture.failNext=true);await panel.locator("#save-settings").click();
  await expect(panel.locator('[role="alert"]')).toBeVisible();await expect(panel.locator('[name="name"]')).toBeDisabled();
  await panel.locator("#save-settings").click();await expect(panel).toContainText("Saved and verified");
  const calls=await page.evaluate(()=>window.fixture.calls.filter(item=>item.action==="settings.patch"));
  expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0].payload).toEqual({revision:1,changes:{name:"Synthetic revised family",language:"en",timezone:"UTC"}});
  await page.route("**/config/integrations/integration/family_assistant",route=>route.fulfill({contentType:"text/html",body:"<title>Synthetic native setup boundary</title>"}));
  await native.click();await expect(page).toHaveURL(/\/config\/integrations\/integration\/family_assistant$/);
  await expect(page).toHaveTitle("Synthetic native setup boundary");
});

test("control sweep: task cancellation dismisses safely, retries exact operation and archives history",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&taskedit=1");const card=page.locator("family-assistant-card");
  let item=card.locator(".body > ul.list > li.item").first();
  await item.getByRole("button",{name:"Cancel task",exact:true}).click();await item.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await item.getByRole("button",{name:"Cancel task",exact:true}).click();await page.evaluate(()=>window.failCommand=true);
  await item.getByRole("button",{name:"Confirm cancellation",exact:true}).click();await expect(card.getByRole("alert")).toBeVisible();
  await page.evaluate(()=>window.failCommand=false);await item.getByRole("button",{name:"Retry",exact:true}).click();
  await card.locator(".tasks-archive > summary").click();item=card.locator(".tasks-archive li.item").first();
  await expect(item).toContainText("Cancelled");await item.getByRole("button",{name:"Archive",exact:true}).click();
  await item.getByRole("button",{name:"Cancel",exact:true}).click();
  await card.locator(".tasks-archive > summary").click();
  await item.getByRole("button",{name:"Archive",exact:true}).click();await item.getByRole("button",{name:"Confirm archive",exact:true}).click();
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(3);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0]).toMatchObject({action:"tasks.cancel",payload:{id:"T000001",revision:1}});
  expect(calls[2]).toMatchObject({action:"tasks.archive",payload:{id:"T000001",revision:2}});
  expect(await page.evaluate(()=>window.fixture.tasks[0])).toMatchObject({status:"archived",revision:3,checklist:[{done:false,text:"Check soil"}]});
});

for(const [status,decision,role,result] of [["requested","reject","owner","rejected"],["requested","cancel","child","cancelled"],["approved","cancel","owner","cancelled"],["fulfilled","refund","owner","refunded"]])test(`control sweep: reward ${status} ${decision} ${role} releases only selected balance`,async({page})=>{
  await page.goto(`/tests/fixtures/dashboard.html?view=court&rewards=1&role=${role}`);
  await page.evaluate(({status})=>{
    const fixture=window.rewardFixture;
    fixture.rewards.requests=[{id:"V000001",name:"Synthetic reviewed reward",cost:10,description:"",member:"child",status,created_at:"2026-09-06T08:00:00Z",revision:4,history:[]}];
    Object.assign(fixture.rewards.balances[0],{reserved:status==="fulfilled"?0:10,spent:status==="fulfilled"?10:0,net:5,available:5});
    window.card._data=structuredClone(fixture);window.card.render();
  },{status});
  const card=page.locator("family-assistant-card"),label=decision[0].toUpperCase()+decision.slice(1);
  if(status==="fulfilled")await card.locator("section.item").filter({has:page.locator("strong").filter({hasText:/^Requests$/})}).locator(":scope > details > summary").click();
  const item=card.locator("li.item").filter({hasText:"Synthetic reviewed reward"});
  await item.getByRole("button",{name:label,exact:true}).click();const form=item.locator("form.editor");
  await form.getByLabel(/Mandatory reason/).fill("Synthetic reviewed decision");
  if(decision==="reject")await page.evaluate(()=>window.failCommand=true);
  await form.locator('button[type="submit"]').click();
  if(decision==="reject"){
    await expect(card.getByRole("alert")).toBeVisible();await expect(form.getByLabel(/Mandatory reason/)).toBeDisabled();
    await page.evaluate(()=>window.failCommand=false);await form.getByRole("button",{name:"Retry",exact:true}).click();
  }
  await expect(form).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls.filter(item=>item.action==="court.reward_transition"));
  expect(calls.at(-1).payload).toEqual({id:"V000001",revision:4,decision,reason:"Synthetic reviewed decision"});
  if(decision==="reject"){expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);}
  const data=await page.evaluate(()=>window.rewardFixture.rewards);
  expect(data.requests[0]).toMatchObject({status:result,revision:5});expect(data.balances[0]).toMatchObject({reserved:0,spent:0,available:15});
  expect(data.balances[1]).toMatchObject({reserved:0,spent:0,available:0});
});

test("control sweep: reward catalog availability, TTL and eligibility save then hide from child",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=court&rewards=1");const card=page.locator("family-assistant-card");
  await card.locator("li.item").filter({hasText:"R000001 · Cinema trip"}).getByRole("button",{name:"Edit",exact:true}).click();
  const form=card.locator("form.editor");await form.getByLabel("Description",{exact:true}).fill("Synthetic private catalog item");
  await form.getByLabel("Request TTL (hours, 1–720)",{exact:true}).fill("24");await form.getByLabel("Available in catalog",{exact:true}).uncheck();
  await form.getByLabel("Child 1",{exact:true}).check();await form.getByRole("button",{name:"Save",exact:true}).click();
  await expect(form).toHaveCount(0);expect(await page.evaluate(()=>window.calls[0].payload)).toMatchObject({id:"R000001",revision:1,description:"Synthetic private catalog item",enabled:false,eligible:["child"],request_ttl_hours:24});
  await page.evaluate(()=>{window.rewardFixture.role="child";window.rewardFixture.actor="child";window.card._data=structuredClone(window.rewardFixture);window.card.render();});
  await expect(card).not.toContainText("Cinema trip");await expect(card.getByRole("button",{name:"New reward",exact:true})).toHaveCount(0);
});

test("control sweep: calendar archive has a cancellable reason review and exact failed retry",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=calendar");const card=page.locator("family-assistant-card"),item=card.locator('[data-calendar-event="E000001"]');
  await item.getByRole("button",{name:"Archive",exact:true}).click();await card.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await item.getByRole("button",{name:"Archive",exact:true}).click();await card.getByLabel("Reason",{exact:true}).fill("Synthetic history retained");
  await page.evaluate(()=>window.failCommand=true);await card.getByRole("button",{name:"Save",exact:true}).click();await expect(card.getByRole("alert")).toBeVisible();
  await page.evaluate(()=>window.failCommand=false);await card.getByRole("button",{name:"Retry",exact:true}).click();
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);expect(calls[0]).toMatchObject({action:"calendar.archive",payload:{id:"E000001",revision:1,reason:"Synthetic history retained"}});
  await expect(card.locator('[data-calendar-agenda]')).not.toContainText("School outing");
  expect(await page.evaluate(()=>window.calendarFixture.calendar.events[0])).toMatchObject({archived:true,revision:2});
});

test("control sweep: court reverse retains reason and child cannot reverse",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=court&courtedit=1");const card=page.locator("family-assistant-card");
  await card.getByRole("button",{name:"Reverse",exact:true}).click();const form=card.locator("form").filter({hasText:"Reverse active record"});
  await form.locator('input[name="reason"]').fill("Synthetic wrong record");await form.getByRole("button",{name:"Reverse",exact:true}).click();
  await expect(form).toHaveCount(0);expect(await page.evaluate(()=>window.calls[0])).toMatchObject({action:"court.reverse",payload:{id:"C000001",revision:1,reason:"Synthetic wrong record"}});
  expect(await page.evaluate(()=>window.courtFixture.court[0])).toMatchObject({status:"reversed",revision:2,reversal:{reason:"Synthetic wrong record"}});
  await page.goto("/tests/fixtures/dashboard.html?view=court&courtedit=1&role=child");await expect(card.getByRole("button",{name:"Reverse",exact:true})).toHaveCount(0);
});

test("control sweep: alarm enable toggles only configuration and failed retry never tests devices",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=alarms");const card=page.locator("family-assistant-card");
  await page.evaluate(()=>window.failCommand=true);await card.getByRole("button",{name:"Disable",exact:true}).click();await expect(card.getByRole("alert")).toBeVisible();
  await page.evaluate(()=>window.failCommand=false);await card.getByRole("button",{name:"Disable",exact:true}).click();await expect(card.getByRole("button",{name:"Enable",exact:true})).toBeVisible();
  await card.getByRole("button",{name:"Enable",exact:true}).click();await expect(card.getByRole("button",{name:"Disable",exact:true})).toBeVisible();
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(3);expect(calls[1]).toEqual(calls[0]);expect(calls.map(item=>item.action)).toEqual(["alarms.enable","alarms.enable","alarms.enable"]);
  expect(calls[0].payload).toEqual({id:"A000001",revision:1,enabled:false});expect(calls[2].payload).toEqual({id:"A000001",revision:2,enabled:true});
  await page.goto("/tests/fixtures/dashboard.html?view=alarms&role=child");await expect(card.getByRole("button",{name:"Disable",exact:true})).toHaveCount(0);
});

test("control sweep: health resolve requires a fresh reason review for an exact repeat without resending",async({page})=>{
  await page.goto("/tests/fixtures/health-view.html?lang=en&role=parent");const card=page.locator("family-health-card");
  await card.getByRole("button",{name:"Resolve without resending",exact:true}).click();
  await card.getByRole("button",{name:"Save",exact:true}).click();expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await card.getByLabel("Reason",{exact:true}).fill("Synthetic issue reviewed without resend");
  await page.evaluate(()=>window.failCommand=true);await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(card.getByRole("alert")).toBeVisible();await page.evaluate(()=>window.failCommand=false);
  // Health currently returns to its action list after failure; it does not
  // retain a draft/retry form. Reopen the reason review explicitly.
  await card.getByRole("button",{name:"Resolve without resending",exact:true}).click();
  await card.getByLabel("Reason",{exact:true}).fill("Synthetic issue reviewed without resend");
  await card.getByRole("button",{name:"Save",exact:true}).click();
  await expect(card.getByRole("button",{name:"Resolve without resending",exact:true})).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0]).toMatchObject({action:"notifications.resolve",payload:{id:"PRIVATE_EVENT_ID_CANARY",reason:"Synthetic issue reviewed without resend"}});
  expect(calls[0].payload).not.toHaveProperty("confirmed");expect(await page.evaluate(()=>window.deliveryResolution.state)).toBe("resolved");
});

test("control sweep: setup packs merge existing modules, Back persists and Finish completes",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=page.locator("family-assistant-panel");
  await panel.locator("#setup-guide").click();await panel.getByRole("button",{name:"Continue",exact:true}).click();
  await panel.getByRole("button",{name:"Continue",exact:true}).click();
  for(const label of ["Family tasks","Motivation","Home helper"]){
    await panel.getByRole("button",{name:`＋ ${label}`,exact:true}).click();await expect(panel).toContainText("Saved and verified");
  }
  const calls=await page.evaluate(()=>window.fixture.calls.filter(item=>item.action==="settings.patch"));
  expect(calls.map(call=>call.payload.revision)).toEqual([1,2,3]);
  expect(calls[2].payload.changes.modules).toEqual(["court","maintenance","pantry","school","shopping","tasks"]);
  await panel.getByRole("button",{name:"Back",exact:true}).click();await expect(panel.locator('[aria-current="step"]')).toContainText("2. Connections");
  await panel.getByRole("button",{name:"Continue",exact:true}).click();await panel.getByRole("button",{name:"Continue",exact:true}).click();
  await panel.getByRole("button",{name:"Finish and open overview",exact:true}).click();
  await expect(panel.locator('[aria-current="step"]')).toHaveCount(0);
  expect(await page.evaluate(()=>window.fixture.data.onboarding)).toMatchObject({step:4,completed:true,skipped:[]});
});

test("control sweep: recognition preview and connection refresh never execute a command",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=page.locator("family-assistant-panel");
  await panel.locator("#panel-refresh").click();
  await panel.locator(".nav-tabs-bar").getByRole("button",{name:/Connections/}).click();
  await panel.locator(".panel-stack").getByRole("button",{name:"Refresh",exact:true}).click();
  await panel.locator('[name="phrase"]').fill("Synthetic child helped with dinner");
  await panel.getByRole("button",{name:"Preview without executing",exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.fixture.calls.filter(item=>item.type==="family_assistant/ai_sandbox_test").length)).toBe(1);
  const calls=await page.evaluate(()=>window.fixture.calls);expect(calls.find(item=>item.type==="family_assistant/ai_sandbox_test")).toMatchObject({entry_id:"synthetic",text:"Synthetic child helped with dinner"});
  expect(calls.filter(item=>item.type==="family_assistant/execute")).toEqual([]);
});

test("control sweep: assignee accepts a task and cancels a draft report without submitting",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&taskedit=1&role=child");const item=page.locator("family-assistant-card .body > ul.list > li.item").first();
  await item.getByRole("button",{name:"Accept",exact:true}).click();await expect(item.locator(".badge")).toHaveText("Accepted");
  await item.getByRole("button",{name:"Send report",exact:true}).click();await item.getByLabel("Report",{exact:true}).fill("Unsubmitted synthetic draft");
  await item.getByRole("button",{name:"Cancel",exact:true}).click();
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(1);expect(calls[0]).toMatchObject({action:"tasks.accept",payload:{id:"T000001",revision:1}});
  expect(await page.evaluate(()=>window.fixture.tasks[0])).toMatchObject({status:"accepted",revision:2,report:null});
});
