import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";

const dom=new JSDOM("<!doctype html><body></body>",{url:"http://localhost"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","FormData"])
  globalThis[key]=dom.window[key];
class OldTasks extends HTMLElement {}
class OldAlarms extends HTMLElement {}
customElements.define("family-tasks-card",OldTasks);
customElements.define("family-alarms-card",OldAlarms);
window.customCards=[{type:"family-tasks-card",name:"Legacy tasks"}];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const {CARD_VIEWS,cardView}=await import("../custom_components/family_assistant/frontend/card-registry.js");

test("preloaded legacy elements and their picker metadata are preserved",()=>{
  assert.equal(customElements.get("family-tasks-card"),OldTasks);
  assert.equal(customElements.get("family-alarms-card"),OldAlarms);
  assert.deepEqual(window.customCards.find(row=>row.type==="family-tasks-card"),
    {type:"family-tasks-card",name:"Legacy tasks"});
  assert.equal(window.customCards.some(row=>row.type==="family-alarms-card"),false);
});

for(const [view,suffix] of CARD_VIEWS)test(`namespaced ${view} card has correct view and editor`,()=>{
  const type=view==="today"?"family-assistant-card":`family-assistant-${suffix}-card`;
  const descriptor=window.customCards.find(row=>row.type===type);
  assert.ok(descriptor?.name.startsWith("Family Assistant · "));
  const Card=customElements.get(type);
  assert.deepEqual(Card.getStubConfig(),{view});
  const card=document.createElement(type);
  card.setConfig({type:`custom:${type}`,entry_id:"synthetic"});
  assert.equal(card._view,view);
  assert.equal(cardView(`custom:${type}`),view);
  const editor=document.createElement("family-assistant-card-editor");
  editor.setConfig({type:`custom:${type}`});
  assert.equal(editor.shadowRoot.querySelector('[name="view"]').value,view);
  card.remove();
});

test("unoccupied legacy names still work but are not advertised",()=>{
  const Card=customElements.get("family-shopping-card");
  assert.deepEqual(Card.getStubConfig(),{view:"shopping"});
  assert.equal(window.customCards.some(row=>row.type==="family-shopping-card"),false);
  assert.equal(cardView("custom:family-shopping-card"),"shopping");
});

test("repeat loading preserves constructors and avoids duplicate picker entries",async()=>{
  const before=window.customCards.map(row=>({...row}));
  const Card=customElements.get("family-assistant-tasks-card");
  await import("../custom_components/family_assistant/frontend/family-assistant.js?registry-repeat");
  assert.deepEqual(window.customCards,before);
  assert.equal(customElements.get("family-assistant-tasks-card"),Card);
});
