import {test,expect} from "./control-audit.js";

const panelRoot=page=>page.locator("family-assistant-panel");
const section=(panel,title)=>panel.locator("section.card").filter({has:panel.page().getByRole("heading",{name:title,exact:true})});
const mutations=page=>page.evaluate(()=>window.fixture.calls.filter(call=>call.type==="family_assistant/execute"));
async function panelState(page){return page.evaluate(()=>structuredClone(window.fixture.data));}
async function tab(panel,label){await panel.locator(".nav-tabs-bar").getByRole("button",{name:new RegExp(label)}).click();}

for(const kind of ["lease","kid"])test(`control sweep: ${kind} plan cancellation retries only its frozen local command`,async({page})=>{
  await page.goto(`/tests/fixtures/dashboard.html?view=mikrotik&write=1${kind==="kid"?"&kids=1":""}`);
  const card=page.locator("family-assistant-card");
  if(kind==="lease"){
    await card.getByRole("button",{name:"Select eligible dynamic leases",exact:true}).click();
    await card.getByRole("button",{name:"Preview selected leases",exact:true}).click();
  }else{
    await card.getByLabel("Children's internet",{exact:true}).selectOption("grant");
    await card.getByLabel("Minutes",{exact:true}).fill("30");
    await card.getByRole("button",{name:"Review plan",exact:true}).click();
  }
  const id=kind==="lease"?"N000001":"K000001",action=`mikrotik.${kind}_cancel`;
  const before=await page.evaluate(({kind})=>{
    const data=window.fixture,bucket=kind==="lease"?data.network:data.kid_control;
    bucket.plans.push({...structuredClone(bucket.plans[0]),id:kind==="lease"?"N000002":"K000002"});
    // Cancellation remains available after expiry and with device writes off.
    bucket.plans[0].expires_at="2000-01-01T00:00:00Z";bucket.writable=false;
    window.card._data=structuredClone(data);window.card.render();
    return structuredClone(data);
  },{kind});
  const plan=card.locator("section.item").filter({has:page.locator("strong").filter({hasText:new RegExp(`^${id} ·`)})});
  const cancel=plan.getByRole("button",{name:kind==="lease"?"Cancel plan":"Cancel",exact:true});
  await expect(plan.getByRole("button",{name:/^Apply reviewed/})).toHaveCount(0);
  await page.evaluate(()=>window.failCommand=true);await cancel.click();
  await expect(card.getByRole("alert")).toBeVisible();await expect(cancel).toBeEnabled();
  expect(await page.evaluate(()=>window.fixture)).toEqual(before);
  expect(await page.evaluate(action=>window.calls.filter(call=>call.action===action),action)).toHaveLength(1);
  await page.evaluate(()=>window.failCommand=false);await cancel.click();
  await expect(plan.locator("strong")).toContainText("Cancelled");await expect(cancel).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls),attempts=calls.filter(call=>call.action===action);
  expect(attempts).toHaveLength(2);expect(attempts[1]).toEqual(attempts[0]);
  expect(attempts[0]).toMatchObject({type:"family_assistant/execute",entry_id:"synthetic",action,payload:{id}});
  expect(Object.keys(attempts[0].payload)).toEqual(["id"]); // These immutable plans have no revision parameter.
  expect(attempts[0].operation_id).toMatch(/^[0-9a-f-]{36}$/);
  expect(calls.map(call=>call.action)).toEqual([`mikrotik.${kind}_plan`,action,action]);
  const after=await page.evaluate(()=>window.fixture),bucket=kind==="lease"?"network":"kid_control";
  before[bucket].plans[0].status="cancelled";expect(after).toEqual(before);
});

for(const [id,label]of [["tasks","Tasks"],["shopping","Shopping"],["school","School"],["court","Points and rules"]])test(`control sweep: panel ${id} quick action opens only its workspace and back is read-only`,async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page),before=await panelState(page);
  await panel.locator(".panel-quick-grid").getByRole("button",{name:new RegExp(label)}).click();
  const card=panel.locator("family-assistant-card");await expect(card).toBeVisible();
  expect(await card.evaluate(node=>node._config)).toMatchObject({entry_id:"synthetic",view:id});
  expect(await card.evaluate(node=>node._config.member_id)).toBeUndefined();
  await panel.getByRole("button",{name:"← Capabilities",exact:true}).click();
  await expect(card).toHaveCount(0);await expect(panel.locator(".panel-module-card")).toHaveCount(15);
  expect(await panelState(page)).toEqual(before);expect(await mutations(page)).toEqual([]);
});

test("control sweep: panel readiness, configuration chips and workspace aliases preserve settings",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page),before=await panelState(page);
  await section(panel,"Needs attention").locator(".panel-issue").getByRole("button",{name:"Configure",exact:true}).click();
  await expect(panel.locator('[name="school_preparation_time"]')).toHaveValue("18:00");
  await panel.locator(".panel-subtabs").getByRole("button",{name:"Open workspace",exact:true}).click();
  expect(await panel.locator("family-assistant-card").evaluate(node=>node._config.view)).toBe("school");
  await panel.locator(".panel-subtabs").getByRole("button",{name:"Settings",exact:true}).click();
  await expect(panel.locator("family-assistant-card")).toHaveCount(0);
  await section(panel,"Related settings").getByRole("button",{name:"Open workspace",exact:true}).click();
  expect(await panel.locator("family-assistant-card").evaluate(node=>node._config.view)).toBe("school");
  await tab(panel,"Overview");await section(panel,"Capabilities").getByRole("button",{name:/Tasks/}).click();
  await expect(panel.locator("family-assistant-card")).toHaveCount(0);
  await expect(section(panel,"Readiness")).toContainText("Ready");
  expect(await panelState(page)).toEqual(before);expect(await mutations(page)).toEqual([]);
});

test("control sweep: member readiness and all-members navigation keep the intended subject",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);
  await page.evaluate(async()=>{
    window.fixture.data.view.settings.modules.push("alarms");
    window.fixture.data.member_readiness=[{id:"M3",alarms:{enabled:0,issues:["alarm_no_schedule"]}}];
    await window.panel.loadData();
  });
  const before=await panelState(page);
  await section(panel,"Needs attention").locator(".panel-issue").filter({hasText:"Sam Example"}).getByRole("button",{name:"Wake-up alarms",exact:true}).click();
  const card=panel.locator("family-assistant-card");await expect(card).toBeVisible();
  expect(await card.evaluate(node=>node._config)).toMatchObject({view:"alarms",member_id:"M3",entry_id:"synthetic"});
  await panel.getByRole("button",{name:"All members",exact:true}).click();
  expect(await card.evaluate(node=>node._config.member_id)).toBeUndefined();
  await tab(panel,"Members");await panel.getByRole("button",{name:/Sam Example/}).click();
  await panel.getByRole("button",{name:"← Members",exact:true}).click();
  await expect(panel.locator("#member-form")).toHaveCount(0);
  expect(await panelState(page)).toEqual(before);expect(await mutations(page)).toEqual([]);
});

test("control sweep: panel profile Cancel refuses discard then removes only the local draft",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page),before=await panelState(page);
  await panel.getByRole("button",{name:/Sam Example/}).click();await panel.locator('[name="name"]').fill("Unsubmitted synthetic name");
  page.once("dialog",dialog=>dialog.dismiss());await panel.locator("#member-form").getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(panel.locator('[name="name"]')).toHaveValue("Unsubmitted synthetic name");
  expect(await panelState(page)).toEqual(before);expect(await mutations(page)).toEqual([]);
  page.once("dialog",dialog=>dialog.accept());await panel.locator("#member-form").getByRole("button",{name:"Cancel",exact:true}).click();
  await expect(panel.locator("#member-form")).toHaveCount(0);await expect(panel).toContainText("Sam Example");
  expect(await page.evaluate(()=>Object.keys(sessionStorage).filter(key=>key.startsWith("family-assistant:panel-draft:")))).toEqual([]);
  expect(await panelState(page)).toEqual(before);expect(await mutations(page)).toEqual([]);
});

for(const origin of ["attention","advanced"])test(`control sweep: panel ${origin} system-status link opens read-only health`,async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page),before=await panelState(page);
  if(origin==="advanced")await tab(panel,"Advanced");
  await section(panel,origin==="attention"?"Needs attention":"Advanced").getByRole("button",{name:"System status",exact:true}).click();
  const card=panel.locator("family-assistant-card");await expect(card).toBeVisible();
  expect(await card.evaluate(node=>node._config)).toMatchObject({view:"health",entry_id:"synthetic"});
  expect(await panelState(page)).toEqual(before);expect(await mutations(page)).toEqual([]);
});

test("control sweep: invitation clipboard, close and resume never confirm or duplicate enrollment",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);
  await page.evaluate(()=>{
    window.clipboardWrites=[];Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText:async text=>window.clipboardWrites.push(text)}});
  });
  await section(panel,"System status").getByRole("button",{name:"Connections",exact:true}).click();
  await section(panel,"Members").locator(".panel-status-row").filter({hasText:"Sam Example"}).getByRole("button",{name:"Create invitation",exact:true}).click();
  const dialog=panel.getByRole("dialog");await expect(dialog).toBeVisible();const created=await page.evaluate(()=>structuredClone(window.fixture.enrollment));
  const link=await dialog.locator("input[readonly]").inputValue();await dialog.getByRole("button",{name:"Copy",exact:true}).click();
  expect(link).toBe("https://t.me/example_test_bot?start=SYNTHETIC-CODE");expect(await page.evaluate(()=>window.clipboardWrites)).toEqual([link]);
  await expect(panel).toContainText("Copied");await dialog.getByRole("button",{name:"Close",exact:true}).click();
  expect(await page.evaluate(()=>window.fixture.enrollment)).toEqual(created);
  await section(panel,"Telegram").getByRole("button",{name:"Refresh",exact:true}).click();
  await panel.getByRole("button",{name:"Review invitation",exact:true}).click();await expect(dialog).toBeVisible();
  await expect(dialog.locator("input[readonly]")).toHaveCount(0);await expect(dialog.getByRole("button",{name:"Copy",exact:true})).toHaveCount(0);
  const calls=await page.evaluate(()=>window.fixture.calls);
  expect(calls.filter(call=>call.type==="family_assistant/telegram_invite")).toEqual([{type:"family_assistant/telegram_invite",entry_id:"synthetic",member_id:"M3"}]);
  expect(calls.filter(call=>call.type==="family_assistant/telegram_enrollment")).toEqual([{type:"family_assistant/telegram_enrollment",entry_id:"synthetic",enrollment_id:created.id}]);
  expect(calls.filter(call=>call.type==="family_assistant/telegram_enrollment_confirm")).toEqual([]);
  await dialog.press("Escape");await expect(dialog).toHaveCount(0);
  expect(await page.evaluate(()=>window.fixture.data.members.find(member=>member.id==="M3").telegram_linked)).toBe(false);
});

test("control sweep: invitation refresh failure and changed account require new owner consent",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);
  await panel.getByRole("button",{name:/Sam Example/}).click();await panel.locator("#member-form").getByRole("button",{name:"Create invitation",exact:true}).click();
  const dialog=panel.getByRole("dialog");await page.evaluate(()=>{window.fixture.enrollment.state="captured";window.fixture.enrollment.candidate={name:"Synthetic first account",chat_id:123456789,user_id:123456789};});
  await dialog.locator("#refresh-enrollment").click();await dialog.locator('[name="confirm_account"]').check();
  await page.evaluate(()=>window.fixture.failEnrollment=true);await dialog.locator("#refresh-enrollment").click();
  await expect(dialog.getByRole("alert")).toBeVisible();await expect(dialog.locator("#confirm-enrollment")).toBeDisabled();
  expect(await page.evaluate(()=>window.fixture.calls.filter(call=>call.type==="family_assistant/telegram_enrollment_confirm"))).toEqual([]);
  await page.evaluate(()=>window.fixture.enrollment.candidate={name:"Synthetic second account",chat_id:234567890,user_id:234567890});
  await dialog.locator("#refresh-enrollment").click();await expect(dialog).toContainText("Synthetic second account");
  await expect(dialog.locator('[name="confirm_account"]')).not.toBeChecked();await expect(dialog.locator("#confirm-enrollment")).toBeDisabled();
  await dialog.locator('[name="confirm_account"]').check();await dialog.locator("#confirm-enrollment").click();
  await expect(dialog).toContainText("Link confirmed");
  const calls=await page.evaluate(()=>window.fixture.calls),confirms=calls.filter(call=>call.type==="family_assistant/telegram_enrollment_confirm");
  expect(confirms).toEqual([{type:"family_assistant/telegram_enrollment_confirm",entry_id:"synthetic",enrollment_id:"synthetic-enrollment-1",candidate:{chat_id:234567890,user_id:234567890}}]);
  expect(calls.filter(call=>call.type==="family_assistant/telegram_enrollment")).toHaveLength(4);
  expect(await page.evaluate(()=>window.fixture.data.members.find(member=>member.id==="M3").telegram_linked)).toBe(true);
});

test("control sweep: invitation Copy retry clears only its clipboard error and sends no WS mutation",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=panelRoot(page);
  await page.evaluate(()=>{
    window.clipboardAttempts=[];window.failClipboard=true;
    Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText:async value=>{window.clipboardAttempts.push(value);if(window.failClipboard)throw Error("Synthetic clipboard denial");}}});
  });
  await tab(panel,"Connections");await panel.locator("#invite-group").click();const dialog=panel.getByRole("dialog");
  const before=await page.evaluate(()=>structuredClone(window.fixture.enrollment));
  await dialog.getByRole("button",{name:"Copy",exact:true}).click();await expect(dialog.getByRole("alert")).toBeVisible();
  await page.evaluate(()=>window.failClipboard=false);await dialog.getByRole("button",{name:"Copy",exact:true}).click();
  await expect(panel).toContainText("Copied");await expect(dialog.getByRole("alert")).toHaveCount(0);
  expect(await page.evaluate(()=>window.clipboardAttempts)).toEqual(["/family_setup@example_test_bot SYNTHETIC-CODE","/family_setup@example_test_bot SYNTHETIC-CODE"]);
  expect(await page.evaluate(()=>window.fixture.enrollment)).toEqual(before);expect(await mutations(page)).toEqual([]);
  expect(await page.evaluate(()=>window.fixture.calls.filter(call=>call.type.startsWith("family_assistant/telegram_")))).toEqual([{type:"family_assistant/telegram_invite",entry_id:"synthetic",kind:"group"}]);
});
