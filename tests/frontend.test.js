import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";

const dom=new JSDOM("<!doctype html><body></body>",{url:"http://localhost"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","FormData"])
  globalThis[key]=dom.window[key];
const {COPY}=await import("../custom_components/family_assistant/frontend/family-assistant.js");
const base={revision:1,settings:{name:"Demo family",modules:["shopping","tasks","court","alarms"]},actor:"parent",role:"parent",
  members:[{id:"parent",name:"Parent",role:"parent",active:true},{id:"child",name:"Child",role:"child",active:true}],
  tasks:[],shopping:[],court:[],alarms:[],alarm_runs:[]};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

test("all frontend locales have identical keys",()=>{
  for(const locale of Object.values(COPY))assert.deepEqual(Object.keys(locale).sort(),Object.keys(COPY.en).sort());
});
test("shopping names never become HTML",async()=>{
  const card=document.createElement("family-shopping-card");card.setConfig({entry_id:"demo"});
  card.hass={language:"en",callWS:async()=>({...base,shopping:[{id:"S1",name:"<img src=x onerror=alert(1)>",quantity:1,purchased:0,unit:"",status:"approved",revision:1}]})};
  await tick();assert.equal(card.shadowRoot.querySelector("img"),null);
  assert.match(card.shadowRoot.textContent,/<img src=x/);
});
test("child does not get parent approval controls",async()=>{
  const card=document.createElement("family-court-card");card.setConfig({entry_id:"demo"});
  card.hass={language:"uk",callWS:async()=>({...base,role:"child",actor:"child",court:[{id:"C1",member:"child",reason:"Example",points:1,status:"active"}]})};
  await tick();assert.equal(card.shadowRoot.querySelectorAll("button").length,0);
});
test("unlinked household shows onboarding hint",async()=>{
  const card=document.createElement("family-shopping-card");card.setConfig({});
  card.hass={language:"ru",callWS:async()=>[]};await tick();
  assert.match(card.shadowRoot.textContent,/Нет привязанной семьи/);
});
test("retry reuses the operation ID after uncertain network result",async()=>{
  const calls=[];let fail=true;const card=document.createElement("family-shopping-card");card.setConfig({entry_id:"demo"});
  card.hass={language:"en",callWS:async(msg)=>{
    if(msg.type.endsWith("/execute")){calls.push(msg);if(fail)throw new Error("Disconnected");return {};}
    return base;
  }};await tick();await card.command("shopping.add",{name:"Milk"});fail=false;
  await card.command("shopping.add",{name:"Milk"});
  assert.equal(calls.length,2);assert.equal(calls[0].operation_id,calls[1].operation_id);
});
test("late response from previous household cannot replace current household",async()=>{
  const card=document.createElement("family-shopping-card");let finish;
  card.setConfig({entry_id:"old"});card.hass={language:"en",callWS:()=>new Promise(resolve=>{finish=resolve;})};
  card.setConfig({entry_id:"new"});finish(base);await tick();assert.equal(card._data,null);
});
