import assert from "node:assert/strict";
import {test,afterEach} from "node:test";
import {JSDOM} from "jsdom";
const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","Event","FormData"])globalThis[key]=dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const {openAlarmEditor}=await import("../custom_components/family_assistant/frontend/alarm-editor.js");
const {SCHOOL_COPY}=await import("../custom_components/family_assistant/frontend/school-copy.js");
const {SCHOOL_WORK_COPY}=await import("../custom_components/family_assistant/frontend/school-work-copy.js");
const clone=value=>structuredClone(value),tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const members=[{id:"owner",name:"Example Owner",role:"owner",active:true,revision:1},{id:"child-a",name:"Child Alpha",role:"child",active:true,revision:2},{id:"child-b",name:"Child Bravo",role:"child",active:true,revision:3}];
const alarm=(id,member)=>({id,member,name:`Wake ${member}`,revision:1,time:"07:00",timezone:"UTC",days:[0,1,2,3,4],enabled:true,exceptions:[],profile:"gentle",second_min:12,second_max:18,recheck_grace:60,penalty:0});
const timetable=(id,member)=>({id,member,title:`Timetable ${member}`,revision:1,status:"active",valid_from:"2026-09-01",valid_until:null,exceptions:[],lessons:[{weekday:0,start:"08:00",end:"09:00",subject:`Subject ${member}`,materials:[]}],backpack_routine:null,history:[]});
function state(){return {revision:1,role:"owner",actor:"owner",members:clone(members),settings:{name:"Example Family",timezone:"UTC",modules:["school","tasks","alarms","digests"]},tasks:[],alarms:[alarm("A1","child-a"),alarm("A2","child-b")],alarm_runs:[{id:"R2",member:"child-b",stage:"first",test:true}],school:{timetables:[timetable("ST1","child-a"),timetable("ST2","child-b")],upcoming:[{id:"U1",member:"child-a",date:"2026-09-14",start:"08:00",end:"09:00",subject:"Alpha upcoming",materials:[]},{id:"U2",member:"child-b",date:"2026-09-14",start:"10:00",end:"11:00",subject:"Bravo upcoming",materials:[]}],homework:[{id:"T1",assignee:"child-a",assignee_revision:2,title:"Alpha homework",revision:1,status:"assigned",checklist:[]},{id:"T2",assignee:"child-b",assignee_revision:3,title:"Bravo homework",revision:1,status:"assigned",checklist:[]}],preparations:[],preparation_reminders:{policy:{enabled:true,days_before:1,time:"19:00",timezone:"UTC"},self_targets:members.slice(1).map(member=>({member:member.id,member_revision:member.revision,recipient_revision:1,subscription_revision:null,enabled:false}))}},digests:{policy:{timezone:"UTC",morning:{enabled:true,time:"07:00"},evening:{enabled:false,time:"19:00"},weekly:{enabled:true,weekday:6,time:"18:00"}},self:{recipient_revision:1,subscription_revision:1,morning:true,evening:false,weekly:false,can_edit:true,health:"ok"}}};}
async function cardFor(view,memberId="child-a",data=state(),extra={}){
  const calls=[],card=document.createElement("family-assistant-card");card.setConfig({entry_id:"example",view,member_id:memberId,...extra});document.body.append(card);
  card.hass={user:{id:"example-owner"},language:"en",callWS:async message=>{calls.push(clone(message));if(message.type==="family_assistant/view")return clone(data);if(message.type==="family_assistant/execute")return {};throw new Error("Unexpected endpoint");}};await tick();return {card,calls,data};
}
afterEach(()=>document.body.replaceChildren());
test("selected school scope filters siblings but preserves actor and recipient identity",async()=>{
  const {card}=await cardFor("school");const text=card.shadowRoot.textContent;assert.match(text,/Settings for: Child Alpha/);assert.match(text,/Alpha upcoming/);assert.match(text,/Alpha homework/);assert.doesNotMatch(text,/Bravo upcoming|Bravo homework|Timetable child-b/);assert.equal(card.shadowRoot.querySelectorAll("[data-school-reminder-member]").length,1);assert.match(card.shadowRoot.querySelector(".school-reminder-recipient").textContent,/Example Owner/);assert.equal(card._data.members.length,3);
});
test("selected child's new timetable form has exactly that child as its target",async()=>{
  const data=state();data.school.timetables=data.school.timetables.filter(item=>item.member!=="child-a");const {card}=await cardFor("school","child-a",data);
  [...card.shadowRoot.querySelectorAll("button")].find(button=>button.textContent===SCHOOL_COPY.en.new_timetable).click();
  const options=[...card.shadowRoot.querySelector('[data-school-form="edit"] [name="member"]').options];assert.deepEqual(options.map(option=>option.value),["child-a"]);
});
test("homework creation defaults to selected child even when a sibling sorts first",async()=>{
  const {card}=await cardFor("school","child-b");[...card.shadowRoot.querySelectorAll("button")].find(button=>button.textContent===SCHOOL_WORK_COPY.en.new_homework).click();
  const select=card.shadowRoot.querySelector('[data-school-work-editor] [name="member"]');assert.equal(select.value,"child-b");assert.deepEqual([...select.options].map(option=>option.value),["child-b"]);
});
test("reminder subsection has only selected child and identified signed-in recipient",async()=>{
  const {card}=await cardFor("school","child-b",state(),{school_section:"reminders"});assert.equal(card.shadowRoot.querySelectorAll(".school-work,.school-section").length,0);assert.equal(card.shadowRoot.querySelector('[data-school-reminder-member]').dataset.schoolReminderMember,"child-b");assert.match(card.shadowRoot.textContent,/Example Owner/);
});
test("alarms list, runs and create selector remain within selected member",async()=>{
  const {card}=await cardFor("alarms");assert.match(card.shadowRoot.textContent,/Wake child-a/);assert.doesNotMatch(card.shadowRoot.textContent,/Wake child-b|Child Bravo/);assert.equal(openAlarmEditor(card),true);assert.deepEqual([...card.shadowRoot.querySelector('[name="member"]').options].map(option=>option.value),["child-a"]);
});
test("command guard rejects sibling targets and reassigning sibling's alarm to selected child",async()=>{
  const {card,calls}=await cardFor("alarms");await card.command("alarms.enable",{id:"A2",revision:1,enabled:false});await card.command("alarms.cancel",{id:"R2",reason:"wrong child"});await card.command("alarms.save",{id:"A2",member:"child-a"});assert.equal(calls.filter(item=>item.type==="family_assistant/execute").length,0);
  await card.command("alarms.enable",{id:"A1",revision:1,enabled:false});assert.equal(calls.filter(item=>item.type==="family_assistant/execute").length,1);
});
test("school command guard rejects sibling timetable, homework and subscription",async()=>{
  const {card,calls}=await cardFor("school");for(const [action,payload]of [["school.timetable_archive",{id:"ST2"}],["school.timetable_save",{id:"ST2",member:"child-a"}],["school.homework_revise",{id:"T2"}],["school.preparation_reminder_access_set",{member:"child-b"}]])await card.command(action,payload);assert.equal(calls.filter(item=>item.type==="family_assistant/execute").length,0);
});
test("digest context never impersonates another recipient or edits owner's subscription",async()=>{
  const {card,calls}=await cardFor("digests","child-a");assert.match(card.shadowRoot.textContent,/only by their recipient/);assert.equal(card.shadowRoot.querySelector("form,.digests"),null);await card.command("digests.access_set",{morning:false});assert.equal(calls.filter(item=>item.type==="family_assistant/execute").length,0);
});
test("own digest context keeps the existing self subscription workflow",async()=>{
  const {card}=await cardFor("digests","owner");assert.ok(card.shadowRoot.querySelector(".digests"));assert.match(card.shadowRoot.querySelector(".member-context").textContent,/Example Owner/);
});
test("revoked or absent focused member removes actions instead of falling back to sibling",async()=>{
  const data=state();data.members[1].active=false;const {card,calls}=await cardFor("alarms","child-a",data);assert.match(card.shadowRoot.textContent,/no longer active/);assert.equal(card.shadowRoot.querySelectorAll("button").length,0);await card.command("alarms.enable",{id:"A1",enabled:false});assert.equal(calls.filter(item=>item.type==="family_assistant/execute").length,0);
});
test("child context cannot select a sibling even if names appear in family roster",async()=>{
  const data=state();data.role="child";data.actor="child-a";const {card}=await cardFor("school","child-b",data);assert.match(card.shadowRoot.textContent,/unavailable to your account/);assert.equal(card.shadowRoot.querySelectorAll("button").length,0);
});
