import {test,expect} from "./control-audit.js";

test("compact tasks card completes and reopens with checkboxes only",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&compact=1");
  const card=page.locator("family-assistant-card");
  await expect(card.locator(".compact-list")).toBeVisible();
  expect(await card.getByRole("button").count()).toBe(0);
  const rows=card.locator(".compact-row");
  await expect(rows).toHaveCount(2);
  expect(await rows.locator(".compact-title").allTextContents()).toEqual(["Water the plants","Read the chapter"]);
  expect(await rows.locator("input[type=checkbox]").nth(0).isChecked()).toBe(false);
  expect(await rows.locator("input[type=checkbox]").nth(1).isChecked()).toBe(true);
  await rows.nth(0).locator("input[type=checkbox]").check();
  let calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("tasks.complete");
  expect(calls[0].payload).toEqual({id:"T000001",revision:1});
  const completed=card.locator(".compact-row").filter({hasText:"Water the plants"});
  await completed.locator("input[type=checkbox]").uncheck();
  calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].action).toBe("tasks.reopen");
  expect(calls[1].payload).toEqual({id:"T000001",revision:2});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("compact alarms card toggles alarms.enable with exact payload",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=alarms&compact=1");
  const card=page.locator("family-assistant-card");
  await expect(card.locator(".compact-list")).toBeVisible();
  expect(await card.getByRole("button").count()).toBe(0);
  const row=card.locator(".compact-row");
  await expect(row).toHaveCount(1);
  expect(await row.locator(".compact-title").textContent()).toBe("07:30");
  expect(await row.locator(".compact-meta").textContent()).toContain("Weekdays");
  const box=row.locator("input[type=checkbox]");
  expect(await box.isChecked()).toBe(true);
  await box.uncheck();
  let calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("alarms.enable");
  expect(calls[0].payload).toEqual({id:"A000001",revision:1,enabled:false});
  await box.check();
  calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].action).toBe("alarms.enable");
  expect(calls[1].payload).toEqual({id:"A000001",revision:2,enabled:true});
});

test("compact editor checkbox emits and removes the compact config flag",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=tasks");
  const card=page.locator("family-assistant-card");
  await expect(card).toBeVisible();
  await expect(card.locator(".compact-list")).toBeVisible();
  await page.evaluate(()=>{
    window.editorCalls=[];window.configChanges=[];const editor=document.createElement("family-assistant-card-editor");window.editor=editor;
    editor.setConfig({type:"custom:family-tasks-card",entry_id:"first",title:"Initial synthetic title"});
    editor.addEventListener("config-changed",event=>window.configChanges.push(structuredClone(event.detail.config)));
    editor.hass={language:"en",connection:{},callWS:async message=>{window.editorCalls.push(message);if(message.type!=="family_assistant/households")throw Error("Unexpected request");return [{entry_id:"first",title:"Synthetic first"}];}};document.querySelector("main").append(editor);
  });
  const editor=page.locator("family-assistant-card-editor");
  const compact=editor.locator("label.check",{hasText:"Compact checklist view"}).locator("input[type=checkbox]");
  expect(await compact.isChecked()).toBe(true);
  await compact.uncheck();
  let changes=await page.evaluate(()=>window.configChanges);
  expect(changes).toEqual([{type:"custom:family-tasks-card",entry_id:"first",title:"Initial synthetic title",compact:false}]);
  await compact.check();
  changes=await page.evaluate(()=>window.configChanges);
  expect(changes).toEqual([
    {type:"custom:family-tasks-card",entry_id:"first",title:"Initial synthetic title",compact:false},
    {type:"custom:family-tasks-card",entry_id:"first",title:"Initial synthetic title"},
  ]);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("active wake-up check forces the full alarms panel despite compact default",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=alarms&ringing=1&compact=1");
  const card=page.locator("family-assistant-card");
  expect(await card.locator(".compact-list").count()).toBe(0);
  await expect(card.getByRole("button",{name:"Stop this wake-up check",exact:true})).toBeVisible();
});
