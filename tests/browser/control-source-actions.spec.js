import {test,expect} from "./control-audit.js";
import {DOCUMENT_COPY} from "../../custom_components/family_assistant/frontend/asset-document-copy.js";
import {TASK_BATCH_COPY} from "../../custom_components/family_assistant/frontend/task-batch-copy.js";
import {TASK_FORM_COPY} from "../../custom_components/family_assistant/frontend/task-form.js";

test("source controls: removed document pagination is bounded and read-only",async({page})=>{
  await page.goto("/tests/fixtures/maintenance.html?lang=en");const section=page.locator("family-maintenance-card .asset-documents").first();await expect(section).toBeVisible();
  await page.evaluate(async()=>{
    const asset=window.fixture.maintenance.assets[0];window.fixture.maintenance.documents=Array.from({length:23},(_,i)=>({id:`MD${i+1}`,asset_id:asset.id,title:`Removed synthetic document ${i+1}`,kind:"manual",status:"deleted",revision:2}));await window.card.refresh();
  });
  const before=await page.evaluate(()=>structuredClone(window.fixture));await expect(section.locator("[data-document-id]")).toHaveCount(20);
  await section.getByRole("button",{name:DOCUMENT_COPY.en.more,exact:true}).click();await expect(section.locator("[data-document-id]")).toHaveCount(23);
  await expect(section.getByRole("button",{name:DOCUMENT_COPY.en.more,exact:true})).toHaveCount(0);
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.fixture)).toEqual(before);
});

test("source controls: task batch pagination reveals eligible rows without changing selection or sending commands",async({page})=>{
  await page.goto("/tests/fixtures/task-batch.html?lang=en");const section=page.locator(".task-batch"),copy=TASK_BATCH_COPY.en;await expect(section).toBeVisible();
  await page.evaluate(async()=>{const sample=window.fixture.tasks[0];window.fixture.tasks=Array.from({length:105},(_,i)=>({...structuredClone(sample),id:`T${String(i+1).padStart(6,"0")}`,title:`Synthetic paged task ${i+1}`}));await window.card.refresh();});
  const before=await page.evaluate(()=>structuredClone(window.fixture.tasks));await section.locator("summary").click();await section.getByRole("button",{name:copy.startBatch,exact:true}).click();
  await expect(section.locator('[name="task_select"]')).toHaveCount(100);await section.locator('[name="task_select"][value="T000001"]').check();
  await section.getByRole("button",{name:copy.loadMore,exact:true}).click();await expect(section.locator('[name="task_select"]')).toHaveCount(105);
  await expect(section.locator('[name="task_select"]:checked')).toHaveCount(1);await expect(section.locator('[name="task_select"][value="T000001"]')).toBeChecked();
  expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.fixture.tasks)).toEqual(before);
});

test("source controls: unavailable recurring assignee is removed only from the unsaved editor",async({page})=>{
  await page.goto("/tests/fixtures/task-series.html?lang=en&actor=parent");const card=page.locator("family-tasks-card");await expect(card.getByRole("button",{name:"Review and edit",exact:true})).toBeVisible();
  await page.evaluate(async()=>{const raw=window.seriesFixture;raw.members.find(m=>m.id==="child").active=false;raw.task_series[0].assignees.push("adult");raw.task_series[0].assignee_revisions.adult=2;await window.card.refresh();});
  const before=await page.evaluate(()=>structuredClone(window.seriesFixture.task_series));await card.getByRole("button",{name:"Review and edit",exact:true}).click();
  const form=card.locator(".task-series-form");await expect(form.locator(".task-series-unavailable")).toHaveCount(1);
  await form.getByRole("button",{name:"Remove unavailable member",exact:true}).click();await expect(form.locator(".task-series-unavailable")).toHaveCount(0);
  expect(await page.evaluate(()=>window.card._taskSeriesDraft.values.assignees)).toEqual(["adult"]);
  await form.getByRole("button",{name:"Cancel",exact:true}).click();
  expect(await page.evaluate(()=>window.seriesFixture.task_series)).toEqual(before);expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("source controls: Lovelace editor emits exact local config changes and only reads authorized households",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=tasks");await expect(page.locator("family-assistant-card")).toBeVisible();
  await page.evaluate(()=>{
    window.editorCalls=[];window.configChanges=[];const editor=document.createElement("family-assistant-card-editor");window.editor=editor;
    editor.setConfig({type:"custom:family-tasks-card",entry_id:"first",title:"Initial synthetic title",member_id:"child"});
    editor.addEventListener("config-changed",event=>window.configChanges.push(structuredClone(event.detail.config)));
    editor.hass={language:"en",connection:{},callWS:async message=>{window.editorCalls.push(message);if(message.type!=="family_assistant/households")throw Error("Unexpected request");return [{entry_id:"first",title:"Synthetic first"},{entry_id:"second",title:"Synthetic second"}];}};document.querySelector("main").append(editor);
  });
  const editor=page.locator("family-assistant-card-editor");await editor.locator('[name="entry_id"]').selectOption("second");
  await editor.locator('[name="title"]').fill("Changed synthetic title");await editor.locator('[name="title"]').press("Tab");await editor.locator('[name="view"]').selectOption("school");
  const changes=await page.evaluate(()=>window.configChanges);expect(changes).toEqual([
    {type:"custom:family-tasks-card",entry_id:"second",title:"Initial synthetic title",member_id:"child"},
    {type:"custom:family-tasks-card",entry_id:"second",title:"Changed synthetic title",member_id:"child"},
    {type:"custom:family-tasks-card",entry_id:"second",title:"Changed synthetic title",member_id:"child",view:"school"},
  ]);expect(await page.evaluate(()=>window.editorCalls)).toEqual([{type:"family_assistant/households"}]);expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("source controls: panel household selector replaces context using only the selected authorized entry",async({page})=>{
  await page.goto("/tests/fixtures/panel.html?lang=en");const panel=page.locator("family-assistant-panel");await expect(panel.locator("#panel-refresh")).toBeVisible();
  await page.evaluate(()=>{
    const original=window.panel._hass,first=structuredClone(window.fixture.data);window.panelReadCalls=[];
    window.panel.hass={...original,connection:{},callWS:async message=>{
      window.panelReadCalls.push(structuredClone(message));
      if(message.type==="family_assistant/households")return [{entry_id:"first",title:"Synthetic first"},{entry_id:"second",title:"Synthetic second"}];
      if(message.type!=="family_assistant/panel"||!["first","second"].includes(message.entry_id))throw Error("Unexpected request");
      return {...structuredClone(first),view:{...structuredClone(first.view),settings:{...first.view.settings,name:message.entry_id==="first"?"Synthetic first":"Synthetic second"}}};
    }};
  });
  const selector=panel.locator("header select");await expect(selector).toBeEnabled();await selector.selectOption("first");
  await expect(panel.locator("header")).toContainText("Synthetic first");await selector.selectOption("second");await expect(panel.locator("header")).toContainText("Synthetic second");
  expect(await page.evaluate(()=>window.panel._entry)).toBe("second");
  expect(await page.evaluate(()=>window.panelReadCalls)).toEqual([{type:"family_assistant/households"},{type:"family_assistant/panel",entry_id:"first"},{type:"family_assistant/panel",entry_id:"second"}]);
});

test("source controls: parent alarm Stop validates a reason and retries the same local cancellation",async({page})=>{
  await page.goto("/tests/fixtures/dashboard.html?view=alarms&ringing=1");const card=page.locator("family-assistant-card"),label="Stop this wake-up check";await expect(card.getByRole("button",{name:label,exact:true})).toBeVisible();
  await page.evaluate(()=>{
    const original=window.card._hass;window.alarmCancelCalls=[];window.failAlarmCancel=true;
    window.card.hass={...original,callWS:async message=>{
      if(message.action!=="alarms.cancel")return original.callWS(message);window.alarmCancelCalls.push(structuredClone(message));
      if(window.failAlarmCancel)throw {code:"storage_error"};
      const p=message.payload,run=window.fixture.alarm_runs.find(r=>r.id===p.id);
      if(window.fixture.role!=="owner"||Object.keys(p).sort().join(",")!=="id,reason"||!p.reason.trim())throw {code:"forbidden"};
      if(!run||!["first","waiting_second","second"].includes(run.stage))throw {code:"invalid_transition"};
      Object.assign(run,{stage:"cancelled",siren_desired:false});return structuredClone(run);
    }};
  });
  const before=await page.evaluate(()=>structuredClone(window.fixture));await card.getByRole("button",{name:label,exact:true}).click();
  let form=card.locator("form").filter({has:page.locator('[name="reason"]')});await form.getByRole("button",{name:label,exact:true}).click();expect(await page.evaluate(()=>window.alarmCancelCalls)).toEqual([]);
  await form.locator('[name="reason"]').fill("Synthetic parent reviewed stop");await form.getByRole("button",{name:label,exact:true}).click();await expect(card.getByRole("alert")).toBeVisible();
  expect(await page.evaluate(()=>window.fixture)).toEqual(before);await page.evaluate(()=>window.failAlarmCancel=false);
  await card.getByRole("button",{name:label,exact:true}).click();form=card.locator("form").filter({has:page.locator('[name="reason"]')});
  await form.locator('[name="reason"]').fill("Synthetic parent reviewed stop");await form.getByRole("button",{name:label,exact:true}).click();await expect(card.getByRole("button",{name:label,exact:true})).toHaveCount(0);
  const calls=await page.evaluate(()=>window.alarmCancelCalls);expect(calls).toHaveLength(2);expect(calls[1]).toEqual(calls[0]);expect(calls[0].payload).toEqual({id:"W000001",reason:"Synthetic parent reviewed stop"});
  before.alarm_runs[0].stage="cancelled";before.alarm_runs[0].siren_desired=false;expect(await page.evaluate(()=>window.fixture)).toEqual(before);expect(await page.evaluate(()=>window.calls)).toEqual([]);
});

test("source controls: single-task Close without rollback retains a committed create after receipt loss",async({page})=>{
  await page.goto("/tests/fixtures/task-multi.html?lang=en");await page.getByRole("button",{name:"Add",exact:true}).click();const form=page.locator("form[data-task-create]");
  await form.locator('[name="title"]').fill("One committed synthetic task");await form.locator('[name="assignee"]').selectOption("first");await page.evaluate(()=>window.loseReplyOnce=true);
  await form.locator('button[type="submit"]').click();await expect(form.getByRole("button",{name:TASK_FORM_COPY.en.closeWithoutRollback,exact:true})).toBeVisible();
  const before=await page.evaluate(()=>structuredClone(window.fixture.tasks));expect(before).toHaveLength(1);
  await form.getByRole("button",{name:TASK_FORM_COPY.en.closeWithoutRollback,exact:true}).click();await expect(form).toHaveCount(0);
  expect(await page.evaluate(()=>window.fixture.tasks)).toEqual(before);expect(await page.evaluate(()=>window.calls)).toHaveLength(1);expect(await page.evaluate(()=>window.calls[0].action)).toBe("tasks.create");
});

test("source controls: failed photo preview Cancel revokes its draft without reservation or upload",async({page})=>{
  await page.clock.setFixedTime(new Date("2026-09-07T07:00:00Z"));await page.goto("/tests/fixtures/task-media-fixture.html?lang=en&actor=child");
  const section=page.locator('[data-task-media-id="T000001"]');await section.locator('input[type="file"]').setInputFiles({name:"broken-synthetic.png",mimeType:"image/png",buffer:Buffer.from("not an image")});
  await section.getByRole("button",{name:"Review selected photo",exact:true}).click();await expect(section.locator(".task-media-review")).toContainText(/preview/i);
  await expect.poll(()=>page.evaluate(()=>window.card._taskMediaDraft?.previewFailed)).toBe(true);
  await section.getByRole("button",{name:"Cancel",exact:true}).click();await expect(section.locator(".task-media-form")).toBeVisible();
  expect(await page.evaluate(()=>window.card._taskMediaDraft)).toBeNull();expect(await page.evaluate(()=>window.calls)).toEqual([]);expect(await page.evaluate(()=>window.httpCalls)).toEqual([]);
});

test("source controls: pantry archive reason is validated and failed save retries without losing stock history",async({page})=>{
  await page.goto("/tests/fixtures/pantry.html?actor=parent");const card=page.locator("family-pantry-card");
  await card.getByRole("button",{name:"Add pantry item",exact:true}).click();await card.getByLabel("Item name",{exact:true}).fill("Synthetic archived pantry item");await card.getByLabel("Unit of measurement",{exact:true}).fill("kg");
  await card.getByRole("button",{name:"Save",exact:true}).click();await expect(card.locator("form")).toHaveCount(0);
  const before=await page.evaluate(()=>structuredClone(window.fixture.pantry.items[0]));await card.getByRole("button",{name:"Archive item",exact:true}).click();let form=card.locator("form");
  await form.getByRole("button",{name:"Archive item",exact:true}).click();expect(await page.evaluate(()=>window.calls)).toHaveLength(1);
  await form.getByLabel("Reason for change",{exact:true}).fill("Synthetic stock history retained");await page.evaluate(()=>window.failCommand=true);await form.getByRole("button",{name:"Archive item",exact:true}).click();
  await expect(form.getByRole("button",{name:"Retry",exact:true})).toBeVisible();expect(await page.evaluate(()=>window.fixture.pantry.items[0])).toEqual(before);
  await page.evaluate(()=>window.failCommand=false);await form.getByRole("button",{name:"Retry",exact:true}).click();await expect(form).toHaveCount(0);
  const calls=await page.evaluate(()=>window.calls);expect(calls).toHaveLength(3);expect(calls[2]).toEqual(calls[1]);expect(calls[1]).toMatchObject({action:"pantry.item_archive",payload:{id:before.id,revision:before.revision,reason:"Synthetic stock history retained"}});
  expect(await page.evaluate(()=>window.fixture.pantry.items[0])).toMatchObject({...before,status:"archived",revision:before.revision+1});
});

test("source controls: manual maintenance log consumable Remove affects only its unsaved row",async({page})=>{
  await page.goto("/tests/fixtures/maintenance.html?lang=en");const card=page.locator("family-maintenance-card");await card.getByRole("button",{name:"Record completed service",exact:true}).click();
  const form=card.locator('[data-maintenance-form="log_edit"]');const before=await page.evaluate(()=>structuredClone(window.fixture));
  await form.getByRole("button",{name:"Add consumable",exact:true}).click();await expect(form.locator(".maintenance-consumable")).toHaveCount(1);
  await form.locator('.maintenance-consumable [name="label"]').fill("Unsent synthetic filter");await form.getByRole("button",{name:"Remove consumable",exact:true}).click();await expect(form.locator(".maintenance-consumable")).toHaveCount(0);
  await form.getByRole("button",{name:"Cancel",exact:true}).click();expect(await page.evaluate(()=>window.fixture)).toEqual(before);expect(await page.evaluate(()=>window.calls)).toEqual([]);
});
