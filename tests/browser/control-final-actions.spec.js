import {test,expect} from "./control-audit.js";
import {DOCUMENT_COPY} from "../../custom_components/family_assistant/frontend/asset-document-copy.js";
import {NETWORK_WATCH_COPY} from "../../custom_components/family_assistant/frontend/network-watch-copy.js";
import {TASK_BATCH_COPY} from "../../custom_components/family_assistant/frontend/task-batch-copy.js";

const panelRoot=page=>page.locator("family-assistant-panel");
const writes=page=>page.evaluate(()=>window.fixture.calls.filter(call=>call.type==="family_assistant/execute"));
const tab=(panel,label)=>panel.locator(".nav-tabs-bar").getByRole("button",{name:new RegExp(label)}).click();
const submit=form=>form.evaluate(node=>node.requestSubmit());

test("final controls: equipment document Cancel discards selected file without upload or reservation",async({page})=>{
  await page.goto("/tests/fixtures/maintenance.html?lang=en");
  const section=page.locator("family-maintenance-card .asset-documents").first(),copy=DOCUMENT_COPY.en;
  const before=await page.evaluate(()=>structuredClone(window.fixture));
  await section.getByRole("button",{name:copy.add,exact:true}).click();
  await section.locator('[name="document_file"]').setInputFiles({name:"synthetic.pdf",mimeType:"application/pdf",buffer:Buffer.from("synthetic pdf")});
  await section.locator('[name="title"]').fill("Unsent synthetic document");
  await section.getByRole("button",{name:copy.cancel,exact:true}).click();
  await expect(section.locator("[data-document-form]")).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.fixture)).toEqual(before);
  expect(await page.evaluate(()=>window.card._assetDocumentDraft)).toBeNull();
  await section.getByRole("button",{name:copy.add,exact:true}).click();
  await expect(section.locator('[name="title"]')).toHaveValue("");
  expect(await section.locator('[name="document_file"]').evaluate(node=>node.files.length)).toBe(0);
});

test("final controls: manual points award validates and retries exactly for the chosen member",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=court&courtedit=1");const card=page.locator("family-assistant-card");
  const initial=await page.evaluate(()=>structuredClone(window.courtFixture.court));
  await card.getByRole("button",{name:"Award or deduct points",exact:true}).click();
  const form=card.locator("form").filter({has:page.locator('[name="points"]')});
  await form.locator('[name="assignee"]').selectOption("child");await form.locator('[name="points"]').fill("0");
  await form.locator('[name="reason"]').fill("Synthetic helpful action");
  await form.getByRole("button",{name:"Save",exact:true}).click();
  await expect(form).toContainText("Points must be a non-zero integer");expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await form.locator('[name="points"]').fill("3");await page.evaluate(()=>window.failCommand=true);
  await form.getByRole("button",{name:"Save",exact:true}).click();await expect(card.getByRole("alert")).toBeVisible();
  await expect(form.locator('[name="points"]')).toBeDisabled();
  expect(await page.evaluate(()=>window.courtFixture.court)).toEqual(initial);
  await page.evaluate(()=>window.failCommand=false);await form.getByRole("button",{name:"Retry",exact:true}).click();
  await expect(form).toHaveCount(0);const calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0]).toMatchObject({action:"court.award",payload:{member:"child",points:3,reason:"Synthetic helpful action"}});
  const after=await page.evaluate(()=>window.courtFixture.court);expect(after.slice(0,-1)).toEqual(initial);
  expect(after.at(-1)).toMatchObject({member:"child",points:3,reason:"Synthetic helpful action",revision:1,status:"active"});
});

test("final controls: panel initial load Retry recovers only through authorized reads",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);await expect(panel.locator("#panel-refresh")).toBeVisible();
  await page.evaluate(async()=>{
    const original=window.panel._hass;window.failPanelRead=true;
    window.panel.hass={...original,connection:{},callWS:async message=>{
      if(message.type==="family_assistant/panel"&&window.failPanelRead){window.fixture.calls.push(structuredClone(message));throw {code:"connection_lost"};}
      return original.callWS(message);
    }};
  });
  await expect(panel.getByRole("button",{name:"Retry",exact:true})).toBeVisible();
  await expect(panel.locator(".panel-member-card")).toHaveCount(0);expect(await writes(page)).toEqual([]);
  const before=await page.evaluate(()=>window.fixture.calls.length);await page.evaluate(()=>window.failPanelRead=false);
  await panel.getByRole("button",{name:"Retry",exact:true}).click();await expect(panel.getByRole("button",{name:/Sam Example/})).toBeVisible();
  expect(await page.evaluate(before=>window.fixture.calls.slice(before),before)).toEqual([{type:"family_assistant/panel",entry_id:"synthetic"}]);
  expect(await writes(page)).toEqual([]);
});

test("final controls: pantry meal shortcut opens meals without changing inventory or settings",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);
  await page.evaluate(async()=>{window.fixture.data.view.settings.modules.push("pantry","meals");await window.panel.loadData();});
  const before=await page.evaluate(()=>structuredClone(window.fixture.data));
  await tab(panel,"Capabilities");await panel.locator(".panel-module-card").filter({has:page.getByRole("heading",{name:/Food and pantry/})}).getByRole("button",{name:"Configure",exact:true}).click();
  await panel.locator(".panel-subtabs").getByRole("button",{name:"🍽️",exact:true}).click();
  const card=panel.locator("family-assistant-card");await expect(card).toBeVisible();
  expect(await card.evaluate(node=>node._config)).toMatchObject({view:"meals",entry_id:"synthetic"});
  expect(await page.evaluate(()=>window.fixture.data)).toEqual(before);expect(await writes(page)).toEqual([]);
});

for(const state of ["expired","superseded"])test(`final controls: ${state} invitation reissues only for its original member without confirming`,async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);
  await panel.getByRole("button",{name:/Sam Example/}).click();await panel.locator("#member-form").getByRole("button",{name:"Create invitation",exact:true}).click();
  const dialog=panel.getByRole("dialog");await expect(dialog).toBeVisible();
  await page.evaluate(state=>{
    const record=window.fixture.enrollment;
    if(state==="expired"){record.state="expired";record.expires_at="2000-01-01T00:00:00Z";}else record.state="superseded";
  },state);
  await dialog.locator("#refresh-enrollment").click();
  await expect(dialog.locator("#confirm-enrollment")).toHaveCount(0);await expect(dialog.getByRole("button",{name:"Copy",exact:true})).toHaveCount(0);
  await dialog.getByRole("button",{name:"Create invitation",exact:true}).click();
  await expect(dialog.locator("input[readonly]")).toHaveValue("https://t.me/example_test_bot?start=SYNTHETIC-CODE");
  const calls=await page.evaluate(()=>window.fixture.calls);
  expect(calls.filter(call=>call.type==="family_assistant/telegram_invite")).toEqual(Array.from({length:2},()=>({type:"family_assistant/telegram_invite",entry_id:"synthetic",member_id:"M3"})));
  expect(calls.filter(call=>call.type==="family_assistant/telegram_enrollment_confirm")).toEqual([]);
  const data=await page.evaluate(()=>window.fixture.data);expect(data.enrollments).toHaveLength(2);
  expect(data.enrollments[0].state).toBe(state);expect(data.enrollments[1]).toMatchObject({id:"synthetic-enrollment-2",member:"M3",state:"issued"});
  expect(data.members.find(member=>member.id==="M3").telegram_linked).toBe(false);expect(await writes(page)).toEqual([]);
});

for(const label of ["Configure Telegram","Configure language assistant"])test(`final controls: ${label} opens only intercepted native setup boundary`,async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);await tab(panel,"Connections");
  expect(await writes(page)).toEqual([]);
  await page.route("**/config/integrations/integration/family_assistant",route=>route.fulfill({contentType:"text/html",body:"<title>Synthetic native configuration boundary</title>"}));
  await panel.getByRole("link",{name:label,exact:true}).click();
  await expect(page).toHaveURL(/\/config\/integrations\/integration\/family_assistant$/);await expect(page).toHaveTitle("Synthetic native configuration boundary");
});

test("final controls: member alternate submit freezes failed save and preserves other members",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page),before=await page.evaluate(()=>structuredClone(window.fixture.data.members));
  await panel.getByRole("button",{name:/Sam Example/}).click();const form=panel.locator("#member-form");
  await form.locator('[name="name"]').fill("Synthetic submitted member");await page.evaluate(()=>window.fixture.failNext=true);await submit(form);
  await expect(panel.getByRole("alert")).toBeVisible();await expect(form.locator('[name="name"]')).toBeDisabled();
  expect(await page.evaluate(()=>window.fixture.data.members)).toEqual(before);await submit(form);await expect(panel).toContainText("Saved and verified");
  const calls=await writes(page);expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);
  expect(calls[0]).toMatchObject({action:"members.save",payload:{id:"M3",revision:3,name:"Synthetic submitted member"}});
  const after=await page.evaluate(()=>window.fixture.data.members);expect(after.slice(0,2)).toEqual(before.slice(0,2));expect(after[2]).toMatchObject({name:"Synthetic submitted member",revision:4});
});

for(const scope of ["advanced","wizard","school"])test(`final controls: ${scope} settings alternate submit writes only reviewed fields`,async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page),before=await page.evaluate(()=>structuredClone(window.fixture.data.view.settings));
  if(scope==="advanced")await tab(panel,"Advanced");
  else if(scope==="wizard")await panel.locator("#setup-guide").click();
  else{await panel.locator("#panel-search").fill("school");await panel.locator(".panel-search-result").first().click();}
  const form=panel.locator("form").filter({has:page.locator("#save-settings")});
  const changes=scope==="school"?{school_preparation_reminders:true,school_preparation_days_before:0,school_preparation_time:"17:45"}:{name:`Synthetic ${scope} family`,language:"en",timezone:"UTC"};
  if(scope==="school"){await form.locator('[name="school_preparation_reminders"]').check();await form.locator('[name="school_preparation_time"]').fill("17:45");}
  else await form.locator('[name="name"]').fill(changes.name);
  await submit(form);await expect(panel).toContainText("Saved and verified");
  const calls=await writes(page);expect(calls).toHaveLength(1);expect(calls[0]).toMatchObject({action:"settings.patch",payload:{revision:1,changes}});
  expect(await page.evaluate(()=>window.fixture.data.view.settings)).toEqual({...before,...changes});
});

test("final controls: recognition alternate submit stays a preview and never executes the recognized award",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);await tab(panel,"Connections");
  const form=panel.locator("form").filter({has:page.locator('[name="phrase"]')});await form.locator('[name="phrase"]').fill("Synthetic helpful action");
  await submit(form);await expect(panel).toContainText("Synthetic helpful action");
  await expect.poll(()=>page.evaluate(()=>window.fixture.calls.filter(call=>call.type==="family_assistant/ai_sandbox_test").length)).toBe(1);
  expect(await page.evaluate(()=>window.fixture.calls.find(call=>call.type==="family_assistant/ai_sandbox_test"))).toEqual({type:"family_assistant/ai_sandbox_test",entry_id:"synthetic",text:"Synthetic helpful action"});
  expect(await writes(page)).toEqual([]);
});

test("final controls: private discovery alternate submit requires consent and sends one exact preference",async({page})=>{
  await page.goto("/tests/fixtures/network-watch.html?lang=en");const section=page.locator("family-network-card .network-watch"),copy=NETWORK_WATCH_COPY.en;
  await section.getByRole("button",{name:copy.enable,exact:true}).click();const form=section.locator("form");
  await form.locator('[name="min_interval_minutes"]').fill("20");await submit(form);expect(await page.evaluate(()=>window.calls)).toEqual([]);
  await form.locator('[name="confirmed"]').check();const before=await page.evaluate(()=>structuredClone(window.fixture));await submit(form);await expect(form).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(1);
  expect(calls[0]).toMatchObject({action:"mikrotik.admission_watch_set",payload:{actor_revision:1,watch_revision:null,enabled:true,min_interval_minutes:20,observation_token:before.network.admission.token}});
  expect(await page.evaluate(()=>window.fixture.network.admission.watch)).toMatchObject({enabled:true,effective:true,min_interval_minutes:20,watch_revision:1});
});

test("final controls: task batch selection submit is only a no-navigation guard",async({page})=>{
  await page.goto("/tests/fixtures/task-batch.html?lang=en");const section=page.locator(".task-batch"),copy=TASK_BATCH_COPY.en;
  await section.locator("summary").click();await section.getByRole("button",{name:copy.startBatch,exact:true}).click();
  await section.locator('[name="task_select"][value="T000001"]').check();const before=await page.evaluate(()=>structuredClone(window.fixture));
  await submit(section.locator(".task-batch-select"));await expect(page).toHaveURL(/task-batch.html\?lang=en$/);
  await expect(section.locator(".task-batch-select")).toBeVisible();await expect(section.locator(".task-batch-review")).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.fixture)).toEqual(before);
});

test("final controls: task photo selection submit cannot bypass explicit photo review",async({page})=>{
  await page.clock.setFixedTime(new Date("2026-09-07T07:00:00Z"));await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  const form=page.locator('family-assistant-card [data-task-media-id="T000001"] .task-media-form');
  await form.locator('input[type="file"]').setInputFiles({name:"synthetic.png",mimeType:"image/png",buffer:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=","base64")});
  const before=await page.evaluate(()=>structuredClone(window.fixture.tasks));await submit(form);
  await expect(form).toBeVisible();await expect(page.locator(".task-media-review")).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.httpCalls)).toEqual([]);expect(await page.evaluate(()=>window.fixture.tasks)).toEqual(before);
});
