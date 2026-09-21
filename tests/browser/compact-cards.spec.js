import {test,expect} from "./control-audit.js";

test("compact tasks card removes via archive and restores completed tasks from history",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=tasks&compact=1");
  const card=page.locator("family-assistant-card");
  await expect(card.locator(".compact-list")).toBeVisible();
  await expect(card.getByRole("button",{name:"Add",exact:true})).toBeVisible();
  await expect(card.getByRole("button",{name:"History",exact:true})).toBeVisible();
  const row=card.locator(".compact-row");
  await expect(row).toHaveCount(1);
  expect(await row.locator(".compact-title").textContent()).toBe("Water the plants");
  expect(await row.locator("input[type=checkbox]").isChecked()).toBe(false);
  await row.getByRole("button",{name:"Remove",exact:true}).click();
  let calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("tasks.archive");
  expect(calls[0].payload).toEqual({id:"T000001",revision:1});
  await expect(card.locator(".compact-row")).toHaveCount(0);
  await expect(card.locator(".body .empty")).toBeVisible();
  await card.getByRole("button",{name:"History",exact:true}).click();
  const history=card.locator(".compact-history");
  await expect(history).toBeVisible();
  const closedRow=history.locator(".compact-row").filter({hasText:"Read the chapter"});
  await expect(closedRow.locator(".compact-title")).toHaveText("Read the chapter");
  await closedRow.getByRole("button",{name:"Restore",exact:true}).click();
  calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(2);
  expect(calls[1].action).toBe("tasks.reopen");
  expect(calls[1].payload).toEqual({id:"T000003",revision:1});
  await expect(card.locator(".compact-list:not(.compact-history) .compact-title")).toHaveText("Read the chapter");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

test("compact alarms card hides disabled alarms, removes via alarms.enable and adds via the editor",async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto("/tests/fixtures/dashboard.html?view=alarms&compact=1");
  const card=page.locator("family-assistant-card");
  await expect(card.locator(".compact-list")).toBeVisible();
  const row=card.locator(".compact-row");
  await expect(row).toHaveCount(1);
  expect(await row.locator(".compact-title").textContent()).toBe("07:30");
  expect(await row.locator(".compact-meta").textContent()).toContain("Weekdays");
  expect(await row.locator("input[type=checkbox]").isChecked()).toBe(true);
  await row.getByRole("button",{name:"Remove",exact:true}).click();
  let calls=await page.evaluate(()=>window.calls);
  expect(calls).toHaveLength(1);
  expect(calls[0].action).toBe("alarms.enable");
  expect(calls[0].payload).toEqual({id:"A000001",revision:1,enabled:false});
  await expect(row).toHaveCount(0);
  await expect(card.locator(".body .empty")).toBeVisible();
  await card.getByRole("button",{name:"Add wake-up schedule",exact:true}).click();
  await expect(card.locator('section.alarm-editor[data-alarm-editor="create"]')).toBeVisible();
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
