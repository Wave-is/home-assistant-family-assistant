import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
import { presenceNotificationState, presenceNotificationTransport } from "./fixtures/presence-notifications-data.js";
const dom = new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","Event","FormData"])
  globalThis[key] = dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const {PRESENCE_NOTIFICATIONS_COPY:COPY}=await import("../custom_components/family_assistant/frontend/presence-notifications-copy.js");
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function settle(predicate){for(let i=0;i<100;i++){if(predicate())return;await tick();}assert.fail("Not settled");}
async function setup(t,{role="parent",language="en"}={}){
  const state=presenceNotificationState(role),calls=[],transport=presenceNotificationTransport(state,calls);
  let lose=false;
  const card=document.createElement("family-presence-card");
  card.setConfig({type:"custom:family-presence-card",entry_id:"synthetic-delivery",language});
  document.body.append(card);t.after(()=>card.remove());
  card.hass={user:{id:`synthetic-${role}`},language,callWS:async message=>{
    const result=transport(message);
    if(lose&&message.type==="family_assistant/execute"){lose=false;throw {code:"response_lost"};}
    return result;
  }};
  await settle(()=>card._data?.actor===role);
  return {card,state,calls,loseResponse(){lose=true;}};
}
const section=card=>card.shadowRoot.querySelector(".presence-notifications");
const button=(root,label)=>[...root.querySelectorAll("button")].find(item=>item.textContent===label);
function open(card,language="en",member="child"){
  const row=section(card).querySelector(`[data-notification-member="${member}"]`);
  assert.ok(row);button(row,COPY[language].enable).click();
  return section(card).querySelector("form");
}
function confirm(form){const box=form.querySelector('[name="confirmed"]');box.checked=true;box.dispatchEvent(new Event("change",{bubbles:true}));}
for(const language of ["ru","uk","en"])test(`${language}: separate reviewed guardian consent uses exact seven-field command`,async t=>{
  const {card,state,calls}=await setup(t,{language});const form=open(card,language);
  assert.equal(calls.length,0);const submit=button(form,COPY[language].save);assert.ok(submit.disabled);
  const input=form.querySelector('[name="max_wait_minutes"]');input.value="45";input.dispatchEvent(new Event("input",{bubbles:true}));
  confirm(form);submit.click();await settle(()=>!card._writing&&calls.length===1);
  assert.deepEqual(calls[0].payload,{member:"child",member_revision:4,binding_revision:7,preference_revision:null,enabled:true,max_wait_minutes:45,actor_member_revision:2});
  assert.equal(calls[0].action,"presence.guardian_notification_access_set");
  assert.equal(state.presence.self.enabled,false);assert.equal(state.presence.notifications.managed[0].enabled,true);
});
for(const role of ["adult","child"])test(`${role}: self consent cannot edit others`,async t=>{
  const {card,calls}=await setup(t,{role});assert.equal(section(card).querySelectorAll("[data-notification-member]").length,1);
  const form=open(card,"en",role);confirm(form);button(form,COPY.en.save).click();await settle(()=>!card._writing&&calls.length===1);
  assert.equal(calls[0].action,"presence.notification_access_set");assert.equal(calls[0].payload.member,role);
});
test("guest and disabled module expose no controls",async t=>{
  const guest=await setup(t,{role:"guest"});assert.equal(section(guest.card),null);
  const {card,state}=await setup(t);state.settings.modules=[];await card.refresh();assert.equal(section(card),null);
});
for(const value of ["", "14", "1441", "15.9", "720.1", "no"])test(`reject noninteger/out-of-range wait ${value}`,async t=>{
  const {card,calls}=await setup(t);const form=open(card);confirm(form);
  const input=form.querySelector('[name="max_wait_minutes"]');input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));
  assert.ok(button(form,COPY.en.save).disabled);
  form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}));await tick();assert.equal(calls.length,0);
});
test("response loss retries identical request and receives one durable preference",async t=>{
  const {card,state,calls,loseResponse}=await setup(t);let form=open(card);confirm(form);loseResponse();
  button(form,COPY.en.save).click();await settle(()=>!card._writing&&card._actionError==="response_lost");
  form=section(card).querySelector("form");assert.ok(form);
  button(form,COPY.en.retry).click();await settle(()=>!card._writing&&calls.length===2);
  assert.deepEqual(calls[0],calls[1]);assert.equal(state.presence.notifications.managed[0].preference_revision,1);
});
for(const drift of ["member","binding","preference","actor","role","module","ha_user","entry"])test(`stale review cannot submit after ${drift} change`,async t=>{
  const {card,state,calls}=await setup(t);const form=open(card);confirm(form);const stale=button(form,COPY.en.save);
  if(drift==="member")state.members.find(item=>item.id==="child").revision++;
  if(drift==="binding")state.presence.notifications.managed[0].binding_revision++;
  if(drift==="preference")state.presence.notifications.managed[0].preference_revision=2;
  if(drift==="actor")state.members.find(item=>item.id==="parent").revision++;
  if(drift==="role")state.role="child";
  if(drift==="module")state.settings.modules=[];
  if(drift==="ha_user")card.hass={...card._hass,user:{id:"different-user"}};
  else if(drift==="entry")card.setConfig({...card._config,entry_id:"different-entry"});
  else await card.refresh();
  stale.dispatchEvent(new Event("click",{bubbles:true}));await tick();assert.equal(calls.length,0);
  assert.equal(card._presenceNotificationsDraft,null);
});
test("removed source still permits explicit withdrawal",async t=>{
  const {card,state,calls}=await setup(t);
  Object.assign(state.presence.notifications.managed[0],{enabled:true,effective:false,source_available:false,preference_revision:1,approved_by:"parent"});
  await card.refresh();const row=section(card).querySelector('[data-notification-member="child"]');
  assert.equal(button(row,COPY.en.edit),undefined);button(row,COPY.en.disable).click();
  const form=section(card).querySelector("form");confirm(form);button(form,COPY.en.save).click();
  await settle(()=>!card._writing&&calls.length===1);assert.equal(calls[0].payload.enabled,false);
});
