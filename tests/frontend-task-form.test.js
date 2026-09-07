import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";
const dom=new JSDOM("<!doctype html><body></body>",{url:"http://localhost"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","FormData"])globalThis[key]=dom.window[key];
const {TASK_FORM_COPY}=await import("../custom_components/family_assistant/frontend/task-form.js");
const {PERSONAL_TASK_COPY}=await import("../custom_components/family_assistant/frontend/personal-task-copy.js");
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const tick=()=>new Promise(r=>setTimeout(r,0));
function make(){
  const card=document.createElement("family-tasks-card");card.setConfig({entry_id:"demo",language:"en"});
  card._hass={language:"en",config:{time_zone:"Pacific/Honolulu"}};
  card._data={actor:"parent",role:"parent",settings:{name:"Demo",timezone:"Europe/Berlin",modules:["tasks"]},
    tasks:[],members:[{id:"parent",name:"Parent",active:true,role:"parent"},{id:"child",name:"Child",active:true,role:"child"},{id:"guest",name:"Guest",active:true,role:"guest"}]};
  card._form=true;card.render();card.calls=[];
  card.command=async(action,payload)=>{card.calls.push({action,payload:structuredClone(payload)});};
  return card;
}
const formOf=card=>card.shadowRoot.querySelector("form[data-task-create]");
function input(card,name,value){const field=formOf(card).elements.namedItem(name);field.value=value;field.dispatchEvent(new dom.window.Event("input",{bubbles:true}));return field;}
async function submit(card){formOf(card).dispatchEvent(new dom.window.Event("submit",{bubbles:true,cancelable:true}));await tick();}

test("task create translates copy and uses household zone rather than browser or HA zone",async()=>{
  for(const lang of ["ru","uk"])assert.deepEqual(Object.keys(TASK_FORM_COPY[lang]).sort(),Object.keys(TASK_FORM_COPY.en).sort());
  const card=make();input(card,"title","Clean table");input(card,"assignee","child");input(card,"due_at","2026-09-07T17:00");input(card,"checklist","Wipe\n\nDry");
  assert.equal(formOf(card).elements.assignee.options.length,2);
  await submit(card);
  assert.deepEqual(card.calls[0],{action:"tasks.create",payload:{title:"Clean table",assignee:"child",due_at:"2026-09-07T15:00:00.000Z",report_type:"text",checklist:["Wipe","Dry"],reminder_minutes:60,grace_minutes:30,penalty:0}});
});

test("DST gap is rejected and fold requires an explicit occurrence",async()=>{
  const card=make();input(card,"title","Task");input(card,"due_at","2025-03-30T02:30");await submit(card);assert.equal(card.calls.length,0);
  input(card,"due_at","2025-10-26T02:30");await submit(card);assert.equal(card.calls.length,0);
  input(card,"due_fold","1");await submit(card);assert.equal(card.calls[0].payload.due_at,"2025-10-26T01:30:00.000Z");
});

test("failed creation retains frozen draft and exact operation ID across rerender",async()=>{
  const card=make();delete card.command;let fail=true;
  card._hass.callWS=async call=>{
    if(call.type==="family_assistant/view")return card._data;
    card.calls.push(structuredClone(call));if(fail)throw {code:"storage_error"};return {};
  };
  input(card,"title","Once");input(card,"due_at","2025-10-26T02:30");input(card,"due_fold","1");
  await submit(card);
  assert.equal(formOf(card).elements.title.value,"Once");assert.equal(formOf(card).elements.title.disabled,true);
  assert.equal(formOf(card).elements.due_fold.value,"1");
  fail=false;await submit(card);
  assert.equal(card.calls.length,2);assert.deepEqual(card.calls[0],card.calls[1]);assert.equal(card._taskCreateDraft,null);
});

test("draft survives refresh but household switch discards it and old form cannot send",async()=>{
  const card=make();input(card,"title","Private");input(card,"checklist","Draft step");card.render();assert.equal(formOf(card).elements.title.value,"Private");
  const stale=formOf(card);card.setConfig({entry_id:"other"});
  assert.equal(card._taskCreateDraft,null);stale.dispatchEvent(new dom.window.Event("submit",{cancelable:true}));await tick();assert.equal(card.calls.length,0);
});

test("guest, inactive assignee and changed household zone cannot submit stale form",async()=>{
  for(const mutation of [c=>c._data.role="guest",c=>c._data.members[1].active=false,c=>c._data.settings.timezone="UTC"]){
    const card=make();input(card,"title","Task");input(card,"assignee","child");mutation(card);await submit(card);assert.equal(card.calls.length,0);
  }
});

test("invalid checklist can be corrected; empty deadline is omitted",async()=>{
  const card=make();input(card,"title","Task");input(card,"checklist",Array(51).fill("Step").join("\n"));await submit(card);assert.equal(card.calls.length,0);
  input(card,"checklist","Valid");input(card,"report_type","none");await submit(card);
  assert.equal(card.calls.length,1);assert.equal("due_at" in card.calls[0].payload,false);assert.equal(card.calls[0].payload.report_type,"none");
});

test("personal reminder form pins self, no report or penalties, and preserves frozen retry",async()=>{
  for(const language of ["ru","uk"])assert.deepEqual(Object.keys(PERSONAL_TASK_COPY[language]),Object.keys(PERSONAL_TASK_COPY.en));
  const card=make();input(card,"title","My appointment");input(card,"assignee","child");
  input(card,"report_type","photo");
  const toggle=formOf(card).elements.personal;toggle.checked=true;toggle.dispatchEvent(new dom.window.Event("change",{bubbles:true}));
  assert.equal(formOf(card).elements.assignee.value,"parent");
  for(const key of ["assignee","report_type","grace_minutes","penalty"])assert.equal(formOf(card).elements[key].disabled,true);
  card.command=async(action,payload)=>{card.calls.push({action,payload:structuredClone(payload)});card._actionError="unconfirmed";};
  await submit(card);
  assert.equal(card.calls[0].payload.personal,true);assert.equal(card.calls[0].payload.report_type,"none");
  assert.equal(card.calls[0].payload.grace_minutes,0);assert.equal(card.calls[0].payload.penalty,0);
  assert.equal(formOf(card).elements.personal.checked,true);
  assert.equal(formOf(card).elements.personal.disabled,true);
  await submit(card);assert.deepEqual(card.calls[0],card.calls[1]);
});

test("personal reminder stale form cannot submit after identity revision changes",async()=>{
  const card=make();card._data.members[0].revision=3;card.render();input(card,"title","Private draft");
  const toggle=formOf(card).elements.personal;toggle.checked=true;toggle.dispatchEvent(new dom.window.Event("input",{bubbles:true}));
  card._data.members[0].revision=4;await submit(card);assert.equal(card.calls.length,0);
});
