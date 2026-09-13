import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";

const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","Event","FormData"])globalThis[key]=dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const {HOME_STATUS_COPY}=await import("../custom_components/family_assistant/frontend/home-status-copy.js");

function family(role="owner",enabled=true){return {actor:role,role,home_status_access:"scope-one",members:[{id:role,role,active:true,revision:1}],settings:{name:"Synthetic household",timezone:"UTC",modules:enabled?["home_status"]:[]},tasks:[],shopping:[],court:[],proposals:[]};}
function snapshot(){return {access_marker:"scope-one",generated_at:"2026-09-13T12:00:00+00:00",config_revision:1,max_age_seconds:300,energy:[{id:"power",label:"Synthetic load",value:-2500,unit:"W",reported_state:null,active:null,quality:"ok",ha_reported_at:"2026-09-13T12:00:00+00:00",freshness_basis:"last_reported",report_age_seconds:0}],active:[],groups:[]};}
function setup(language="en",role="owner",enabled=true){
  const card=document.createElement("family-assistant-home-status-card");
  card.setConfig({entry_id:"synthetic",language});
  const requests=[];let view=family(role,enabled),data=snapshot();
  card._hass={language,user:{id:"synthetic-user"},callWS:async request=>{requests.push(request);return structuredClone(request.type==="family_assistant/view"?view:data);}};
  return {card,requests,setView(value){view=value;},setSnapshot(value){data=value;}};
}

for(const language of ["en","ru","uk"])test(`current factual read and refresh are localized ${language}`,async()=>{
  const {card,requests}=setup(language);await card.refresh();
  assert.deepEqual(requests.map(row=>row.type),["family_assistant/view","family_assistant/home_status"]);
  assert.match(card.shadowRoot.textContent,/-2500 W/);
  assert.ok(card.shadowRoot.textContent.includes(HOME_STATUS_COPY[language].note));
  assert.equal(card.shadowRoot.querySelectorAll("a,img,iframe").length,0);
  const button=card.shadowRoot.querySelector("[data-home-status-refresh]");
  assert.equal(button.disabled,false);button.click();
  for(let i=0;i<20&&card._loading;i++)await new Promise(resolve=>setTimeout(resolve,1));
  assert.equal(requests.length,4);card.remove();
});

test("disabled and guest cards do not request source values",async()=>{
  for(const [role,enabled]of [["owner",false],["guest",true]]){
    const {card,requests}=setup("en",role,enabled);await card.refresh();
    assert.deepEqual(requests.map(row=>row.type),["family_assistant/view"]);
    assert.doesNotMatch(card.shadowRoot.textContent,/Synthetic load/);card.remove();
  }
});

for(const language of ["en","ru","uk"])test(`all 32 groups and typed facts render safely ${language}`,async()=>{
  const {card,setSnapshot}=setup(language),data=snapshot(),base={...data.energy[0],value:null,unit:null};
  data.groups=Array.from({length:33},(_,i)=>({id:`group_${i}`,title:`Synthetic group ${i}`,rows:[{...base,label:`Row ${i}`,reported_state:"sunny"}]}));
  data.groups[12].rows.push({...base,label:"Event timestamp",reported_timestamp:"2026-09-12T12:00:00+00:00"});
  data.groups[12].rows.push({...base,label:"Camera state",reported_state:"recording"});
  data.groups[12].rows.push({...base,label:"Count",value:12,unit:""});
  data.groups[12].rows.push({...base,label:"Bad timestamp",reported_timestamp:"<img src=x onerror=bad>"});
  setSnapshot(data);await card.refresh();
  const text=card.shadowRoot.textContent;
  assert.ok(text.includes("Synthetic group 31"));assert.ok(!text.includes("Synthetic group 32"));
  assert.ok(text.includes(HOME_STATUS_COPY[language].state_sunny));
  assert.ok(text.includes(HOME_STATUS_COPY[language].state_recording));
  assert.ok(text.includes("12:00:00 UTC"));assert.ok(!text.includes("2026-09-12T12:00:00+00:00"));
  assert.ok(!text.includes("<img"));assert.equal(card.shadowRoot.querySelectorAll("a,img,iframe").length,0);
  assert.ok(!text.includes("12 null"));card.remove();
});

test("other cards never request home observations",async()=>{
  const {card,requests}=setup();card._hass=null;card.setConfig({entry_id:"synthetic",view:"shopping"});
  card._hass={language:"en",user:{id:"owner"},callWS:async request=>{requests.push(request);return family();}};
  await card.refresh();assert.deepEqual(requests.map(row=>row.type),["family_assistant/view"]);card.remove();
});

test("source permission empty read and module revocation clear previous readings",async()=>{
  const {card,setSnapshot,setView}=setup();await card.refresh();assert.match(card.shadowRoot.textContent,/Synthetic load/);
  setSnapshot({...snapshot(),energy:[]});card._homeStatusRequested=true;await card.refresh();
  assert.doesNotMatch(card.shadowRoot.textContent,/Synthetic load/);assert.match(card.shadowRoot.textContent,/No readable configured sources/);
  setSnapshot(snapshot());card._homeStatusRequested=true;await card.refresh();setView(family("owner",false));await card.refresh();
  assert.equal(card._homeStatus,null);assert.doesNotMatch(card.shadowRoot.textContent,/Synthetic load/);card.remove();
});

test("read error suppresses old values and never renders exception text",async()=>{
  const {card}=setup();await card.refresh();
  card._hass.callWS=async request=>{if(request.type==="family_assistant/view")return family();throw new Error("PRIVATE_ERROR_CANARY");};
  card._homeStatusRequested=true;await card.refresh();assert.equal(card._homeStatus,null);
  assert.doesNotMatch(card.shadowRoot.textContent,/Synthetic load|PRIVATE_ERROR_CANARY/);
  assert.match(card.shadowRoot.textContent,/No previous readings/);card.remove();
});

test("late response cannot populate a replacement household",async()=>{
  const {card}=setup();let resolve;
  card._hass.callWS=async request=>request.type==="family_assistant/view"?family():new Promise(done=>{resolve=done;});
  const pending=card.refresh();while(!resolve)await Promise.resolve();
  card._hass=null;card.setConfig({entry_id:"replacement"});resolve(snapshot());await pending;
  assert.equal(card._homeStatus,null);assert.doesNotMatch(card.shadowRoot.textContent,/Synthetic load/);card.remove();
});

test("unknown/stale readings are explanations, not zero or physical claims",async()=>{
  const {card,setSnapshot}=setup();const value=snapshot();
  value.energy[0]={...value.energy[0],quality:"stale",value:null,report_age_seconds:301};
  value.groups=[{id:"room",title:"<img src=x onerror=bad>",rows:[{...value.energy[0],label:"Unverified",quality:"restored"}]}];
  setSnapshot(value);await card.refresh();assert.match(card.shadowRoot.textContent,/HA report is too old|Restored state is unverified/);
  assert.doesNotMatch(card.shadowRoot.textContent,/-2500 W|: 0 W/);assert.equal(card.shadowRoot.querySelectorAll("img").length,0);card.remove();
});

test("real FamilyCard interval performs metadata-only idle refresh, explicit button reads fresh",async()=>{
  const {card,requests,setView}=setup();let tick;
  const original=globalThis.setInterval;globalThis.setInterval=callback=>{tick=callback;return 999;};
  try{card.connectedCallback();}finally{globalThis.setInterval=original;}
  await card.refresh();assert.equal(requests.filter(row=>row.type==="family_assistant/home_status").length,1);
  for(let i=0;i<3;i++){tick();while(card._loading)await new Promise(resolve=>setTimeout(resolve,1));}
  assert.equal(requests.filter(row=>row.type==="family_assistant/home_status").length,1);
  setView({...family(),home_status_access:"replacement-registry-or-acl"});tick();while(card._loading)await new Promise(resolve=>setTimeout(resolve,1));
  assert.equal(card._homeStatus,null);assert.doesNotMatch(card.shadowRoot.textContent,/Synthetic load/);
  assert.equal(requests.filter(row=>row.type==="family_assistant/home_status").length,1);
  card.shadowRoot.querySelector("[data-home-status-refresh]").click();while(card._loading)await new Promise(resolve=>setTimeout(resolve,1));
  assert.equal(requests.filter(row=>row.type==="family_assistant/home_status").length,2);
  assert.equal(card._homeStatus,null); // Read still carries old source identity and is rejected.
  card.disconnectedCallback();card.remove();
});
