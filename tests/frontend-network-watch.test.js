import test from "node:test";
import assert from "node:assert/strict";
import {JSDOM} from "jsdom";
import {watchState,watchTransport} from "./fixtures/network-watch-data.js";
import {NETWORK_WATCH_COPY as COPY} from "../custom_components/family_assistant/frontend/network-watch-copy.js";
const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","Event","FormData"])globalThis[key]=dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function settle(fn){for(let i=0;i<100;i++){if(fn())return;await tick();}assert.fail("Not settled");}
const section=card=>card.shadowRoot.querySelector(".network-watch");
const button=(root,label)=>[...root.querySelectorAll("button")].find(node=>node.textContent===label);
async function setup(t,{role="parent",language="en"}={}){
  const state=watchState(role),calls=[],transport=watchTransport(state,calls);let lose=false;
  const card=document.createElement("family-network-card");card.setConfig({type:"custom:family-network-card",entry_id:"synthetic-watch",language});
  document.body.append(card);t.after(()=>card.remove());card.hass={user:{id:`synthetic-${role}`},language,callWS:async message=>{
    const result=transport(message);if(lose&&message.type==="family_assistant/execute"){lose=false;throw {code:"response_lost"};}return result;
  }};await settle(()=>card._data?.actor===role);return {card,state,calls,loseResponse(){lose=true;}};
}
function open(card,language="en"){button(section(card),COPY[language].enable).click();return section(card).querySelector("form");}
function confirm(form){const input=form.querySelector('[name="confirmed"]');input.checked=true;input.dispatchEvent(new Event("change",{bubbles:true}));}
for(const language of ["en","ru","uk"])test(`${language}: review explicit private baseline and strict cadence`,async t=>{
  const {card,state,calls}=await setup(t,{language});const form=open(card,language);assert.equal(button(form,COPY[language].save).disabled,true);
  const input=form.querySelector('[name="min_interval_minutes"]');input.value="15";input.dispatchEvent(new Event("input",{bubbles:true}));confirm(form);
  button(form,COPY[language].save).click();await settle(()=>!card._writing&&calls.length===1);
  assert.deepEqual(calls[0].payload,{actor_revision:1,watch_revision:null,enabled:true,min_interval_minutes:15,observation_token:"b".repeat(64)});
  assert.equal(state.network.admission.watch.watch_revision,1);assert.equal(section(card).querySelector("form"),null);
});
for(const role of ["adult","child","guest"])test(`${role}: cannot see subscription controls`,async t=>{const {card}=await setup(t,{role});assert.equal(section(card),null);});
for(const value of ["", "0", "4", "1441", "15.5", "abc"])test(`invalid cadence ${value} cannot submit`,async t=>{
  const {card,calls}=await setup(t);const form=open(card);confirm(form);const input=form.querySelector('[name="min_interval_minutes"]');input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));
  assert.equal(button(form,COPY.en.save).disabled,true);form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}));await tick();assert.equal(calls.length,0);
});
test("lost response keeps frozen operation for exact manual replay",async t=>{
  const {card,state,calls,loseResponse}=await setup(t);let form=open(card);confirm(form);loseResponse();button(form,COPY.en.save).click();
  await settle(()=>!card._writing&&card._actionError==="response_lost");form=section(card).querySelector("form");assert.ok(form);assert.equal(form.querySelector('[name="min_interval_minutes"]').disabled,true);
  button(form,COPY.en.retry).click();await settle(()=>!card._writing&&calls.length===2);assert.deepEqual(calls[0],calls[1]);assert.equal(state.network.admission.watch.watch_revision,1);
});
for(const drift of ["module","actor","role","backend","token","watch","ha_user","entry"])test(`old review blocked on ${drift} drift`,async t=>{
  const {card,state,calls}=await setup(t);const form=open(card);confirm(form);const stale=button(form,COPY.en.save);
  if(drift==="module")state.settings.modules=[];
  if(drift==="actor")state.members.find(row=>row.id==="parent").revision++;
  if(drift==="role")state.role="child";
  if(drift==="backend")state.network.admission.backend="c".repeat(64);
  if(drift==="token")state.network.admission.token="c".repeat(64);
  if(drift==="watch")state.network.admission.watch.watch_revision=2;
  if(drift==="ha_user")card.hass={...card._hass,user:{id:"changed"}};
  else if(drift==="entry")card.setConfig({...card._config,entry_id:"changed"});else await card.refresh();
  stale.dispatchEvent(new Event("click",{bubbles:true}));await tick();assert.equal(calls.length,0);assert.equal(card._networkWatchDraft,null);
});
test("withdrawal works without fresh inventory and omits the observation token",async t=>{
  const {card,state,calls}=await setup(t);Object.assign(state.network.admission.watch,{enabled:true,effective:false,watch_revision:1});state.network.admission.status="stale";state.network.admission.token=null;await card.refresh();
  button(section(card),COPY.en.disable).click();const form=section(card).querySelector("form");confirm(form);button(form,COPY.en.save).click();await settle(()=>!card._writing&&calls.length===1);
  assert.deepEqual(calls[0].payload,{actor_revision:1,watch_revision:1,enabled:false,min_interval_minutes:30});
});
test("locale keys agree",()=>{for(const language of ["ru","uk"])assert.deepEqual(Object.keys(COPY[language]).sort(),Object.keys(COPY.en).sort());});

test("stale observations suspend visible monitoring and reconfiguration, not withdrawal",async t=>{
  const {card,state}=await setup(t);Object.assign(state.network.admission.watch,{enabled:true,effective:true,watch_revision:1});
  state.network.admission.status="stale";state.network.admission.token=null;await card.refresh();
  const root=section(card);assert.ok(root.textContent.includes(COPY.en.effective_suspended));assert.ok(!root.textContent.includes(COPY.en.effective_active));
  assert.equal(button(root,COPY.en.configure).disabled,true);assert.equal(button(root,COPY.en.disable).disabled,false);
  assert.ok(root.textContent.includes(COPY.en.fresh_required));
});
