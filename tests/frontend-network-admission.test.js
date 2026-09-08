import test from "node:test";
import assert from "node:assert/strict";
import {JSDOM} from "jsdom";
import {admissionState,admissionTransport,MAC} from "./fixtures/network-admission-data.js";
import {NETWORK_ADMISSION_COPY as COPY} from "../custom_components/family_assistant/frontend/network-admission-copy.js";
const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","Event","FormData"])globalThis[key]=dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function settle(fn){for(let i=0;i<100;i++){if(fn())return;await tick();}assert.fail("Not settled");}
const section=card=>card.shadowRoot.querySelector(".network-admission");
const button=(root,label)=>[...root.querySelectorAll("button")].find(node=>node.textContent===label);
async function setup(t,{role="owner",language="en"}={}){
  const state=admissionState(role),calls=[],transport=admissionTransport(state,calls);let lose=false;
  const card=document.createElement("family-network-card");card.setConfig({type:"custom:family-network-card",entry_id:"synthetic-admission",language});
  document.body.append(card);t.after(()=>card.remove());card.hass={user:{id:`synthetic-${role}`},language,callWS:async message=>{
    const result=transport(message);if(lose&&message.type==="family_assistant/execute"){lose=false;throw {code:"response_lost"};}return result;
  }};await settle(()=>card._data?.actor===role);return {card,state,calls,loseResponse(){lose=true;}};
}
function open(card,language="en") {button(section(card),COPY[language].approve_button).click();return section(card);}
function label(root,value) {const input=root.querySelector('input[type="text"]');input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));}
function check(root) {const input=root.querySelector('input[type="checkbox"]');input.checked=true;input.dispatchEvent(new Event("change",{bubbles:true}));}
for(const language of ["ru","uk","en"])test(`${language}: real card owner previews then applies only reviewed local record`,async t=>{
  const {card,state,calls}=await setup(t,{language});let root=open(card,language);label(root,"Example laptop");
  button(root,COPY[language].preview_button).click();await settle(()=>!card._writing&&calls.length===1);
  assert.deepEqual(calls[0].payload,{actor_revision:1,observation_token:"b".repeat(64),policy_revision:null,changes:[{mac:MAC,approved:true,label:"Example laptop"}]});
  root=section(card);assert.equal(button(root,COPY[language].apply_button).disabled,true);check(root);button(root,COPY[language].apply_button).click();
  await settle(()=>!card._writing&&calls.length===2);assert.deepEqual(calls[1].payload,{id:"NA1",actor_revision:1,confirmed:true});
  assert.equal(state.network.admission.devices[0].status,"approved");assert.equal(state.network.admission.enforcement,false);
  assert.equal(section(card).querySelector("img"),null);assert.ok(section(card).textContent.includes(COPY[language].warning_locally_administered));
});
for(const role of ["parent","adult","child","guest"])test(`${role}: admission has no mutation controls`,async t=>{
  const {card,calls}=await setup(t,{role});if(role==="parent")assert.equal(section(card).querySelectorAll("button").length,0);else assert.equal(section(card),null);
  assert.equal(calls.length,0);
});
test("lost preview reply retries exact immutable request, no duplicate plan",async t=>{
  const {card,state,calls,loseResponse}=await setup(t);label(open(card),"Example laptop");loseResponse();button(section(card),COPY.en.preview_button).click();
  await settle(()=>!card._writing&&card._actionError==="response_lost");assert.ok(card._admissionDraft?.pending);
  assert.equal(section(card).querySelector('input[type="text"]').disabled,true);
  button(section(card),COPY.en.retry_button).click();await settle(()=>!card._writing&&calls.length===2);
  assert.deepEqual(calls[0],calls[1]);assert.equal(state.network.admission.plans.length,1);
});
for(const drift of ["module","actor","role","backend","token","policy","protected","ha_user","entry"])test(`detached review blocked after ${drift} drift`,async t=>{
  const {card,state,calls}=await setup(t);const root=open(card);label(root,"Example laptop");const stale=button(root,COPY.en.preview_button);
  if(drift==="module")state.settings.modules=[];
  if(drift==="actor")state.members[0].revision++;
  if(drift==="role")state.role="parent";
  if(drift==="backend")state.network.admission.backend="c".repeat(64);
  if(drift==="token")state.network.admission.token="c".repeat(64);
  if(drift==="policy")state.network.admission.policy_revision=2;
  if(drift==="protected")state.network.admission.devices[0].status="protected";
  if(drift==="ha_user")card.hass={...card._hass,user:{id:"changed"}};
  else if(drift==="entry")card.setConfig({...card._config,entry_id:"changed"});
  else await card.refresh();
  stale.dispatchEvent(new Event("click",{bubbles:true}));await tick();assert.equal(calls.length,0);assert.equal(card._admissionDraft,null);
});
test("backend change requires explicit archiving consent",async t=>{
  const {card,state,calls}=await setup(t);state.network.admission.backend_changed=true;await card.refresh();label(open(card),"Example laptop");
  assert.equal(button(section(card),COPY.en.preview_button).disabled,true);check(section(card));button(section(card),COPY.en.preview_button).click();
  await settle(()=>!card._writing&&calls.length===1);assert.equal(calls[0].payload.replace_backend,true);
});
test("stale observation and protected devices offer no approve action",async t=>{
  const {card,state}=await setup(t);assert.equal(section(card).querySelectorAll('.network-admission-devices button').length,1);
  state.network.admission.status="stale";state.network.admission.can_edit=false;await card.refresh();assert.equal(section(card).querySelectorAll("button").length,0);
});
test("locale keys agree",()=>{for(const language of ["ru","uk"])assert.deepEqual(Object.keys(COPY[language]).sort(),Object.keys(COPY.en).sort());});
test("apply cannot use an expired plan even before the next automatic refresh",async t=>{
  const {card,calls}=await setup(t);label(open(card),"Example laptop");button(section(card),COPY.en.preview_button).click();
  await settle(()=>!card._writing&&calls.length===1);check(section(card));
  card._data.network.admission.plans[0].expires_at=new Date(Date.now()-1).toISOString();
  button(section(card),COPY.en.apply_button).dispatchEvent(new Event("click",{bubbles:true}));await tick();assert.equal(calls.length,1);
});
test("stale projected plan cannot be confirmed or applied",async t=>{
  const {card,state,calls}=await setup(t);label(open(card),"Example laptop");button(section(card),COPY.en.preview_button).click();
  await settle(()=>!card._writing&&calls.length===1);state.network.admission.plans[0].applicable=false;await card.refresh();
  assert.equal(section(card).querySelector('input[type="checkbox"]').disabled,true);assert.equal(button(section(card),COPY.en.apply_button).disabled,true);
});
test("lost apply response reconciles the exact persisted plan without duplicate mutation",async t=>{
  const {card,state,calls,loseResponse}=await setup(t);label(open(card),"Example laptop");button(section(card),COPY.en.preview_button).click();
  await settle(()=>!card._writing&&calls.length===1);check(section(card));loseResponse();button(section(card),COPY.en.apply_button).click();
  await settle(()=>!card._writing&&calls.length===2);assert.equal(state.network.admission.policy_revision,1);assert.equal(state.network.admission.plans[0].status,"applied");
  assert.equal(card._admissionPlanPending.NA1,undefined);assert.ok(button(section(card),COPY.en.rename_button));
});
