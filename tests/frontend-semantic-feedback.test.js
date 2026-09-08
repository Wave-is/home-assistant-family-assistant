import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";
const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
globalThis.document=dom.window.document;
const {appendProposalFeedback,renderFeedbackJournal,disposeSemanticFeedback,FEEDBACK_COPY}=await import(
  "../custom_components/family_assistant/frontend/semantic-feedback-view.js");
const plan=()=>({id:"P123",status:"pending",preview:"<img src=x onerror=alert(1)>",expires_at:new Date(Date.now()+300000).toISOString()});
const note=()=>({id:"F000001",actor:"child",role:"child",actor_revision:1,category:"wrong_target",
  expected:"<script>PRIVATE_EXPECTED</script>",preview:"PRIVATE_PREVIEW",source:"PRIVATE_SOURCE",source_available:true});
function setup(language="en",role="child"){
  const card=document.createElement("div"),body=document.createElement("div");
  card.append(body);document.body.append(card);
  Object.assign(card,{_entry:"synthetic-entry",_generation:1,_config:{language},_hass:{user:{id:"ha-synthetic"}},
    _data:{actor:"child",role,members:[{id:"child",role,active:true,revision:1}],
      settings:{modules:["conversation"]},proposals:[plan()],semantic_feedback:{available:true,records:[note()]}}});
  card.calls=[];card.command=(action,payload)=>card.calls.push({action,payload});
  return {card,body};
}
const submit=form=>form.dispatchEvent(new dom.window.Event("submit",{bubbles:true,cancelable:true}));
const input=form=>form.dispatchEvent(new dom.window.Event("input",{bubbles:true}));
function fill(form){form.elements.expected.value="Different action";form.elements.source.value="  Exact original\n";form.querySelector("input[type=checkbox]").checked=true;input(form);}

test("three complete translations and explicit consent; no action on render",()=>{
  for(const language of ["en","ru","uk"]){
    assert.deepEqual(Object.keys(FEEDBACK_COPY[language]).sort(),Object.keys(FEEDBACK_COPY.en).sort());
    const {card,body}=setup(language);appendProposalFeedback(card,body,card._data.proposals[0]);
    assert.ok(body.textContent.includes(FEEDBACK_COPY[language].hint));assert.equal(card.calls.length,0);
    const form=body.querySelector("form");form.elements.expected.value="Different action";submit(form);assert.equal(card.calls.length,0);
    fill(form);submit(form);assert.deepEqual(card.calls,[{action:"conversation.reject",payload:{id:"P123",feedback:{category:"wrong_action",expected:"Different action",source:"  Exact original\n"}}}]);
    card.remove();
  }
});
test("entry/user/member/role/module/DOM/proposal drift rejects stale form",()=>{
  for(const change of [c=>c._entry="other",c=>c._generation++,c=>c._hass.user={id:"ha-synthetic"},
    c=>c._data.members[0].revision++,c=>c._data.members[0].active=false,c=>c._data.role="parent",
    c=>c._data.settings.modules=[],c=>c.remove(),c=>c._data.proposals[0].preview="changed",
    c=>c._data.proposals[0].expires_at=new Date(0).toISOString(),c=>c._writing=true]){
    const {card,body}=setup();appendProposalFeedback(card,body,card._data.proposals[0]);const form=body.querySelector("form");fill(form);change(card);submit(form);assert.equal(card.calls.length,0);card.remove();
  }
});
test("failed-write re-render preserves exact note but clears it on identity change",()=>{
  const {card,body}=setup();appendProposalFeedback(card,body,card._data.proposals[0]);let form=body.querySelector("form");fill(form);submit(form);
  body.replaceChildren();appendProposalFeedback(card,body,card._data.proposals[0]);form=body.querySelector("form");
  assert.equal(form.elements.source.value,"  Exact original\n");assert.equal(form.elements.expected.value,"Different action");
  submit(form);assert.deepEqual(card.calls[1],card.calls[0]);
  card._data.members[0].revision++;body.replaceChildren();appendProposalFeedback(card,body,card._data.proposals[0]);
  assert.equal(body.querySelector("form").elements.expected.value,"");
  disposeSemanticFeedback(card);card.remove();
});
test("malformed or expired proposals and guest accounts do not get feedback controls",()=>{
  for(const update of [c=>c._data.proposals[0].expires_at="bad",c=>c._data.proposals[0].expires_at=new Date(0).toISOString(),
    c=>c._data.proposals[0].status="applied",c=>{c._data.role="guest";c._data.members[0].role="guest";},c=>c._data.members[0].revision=0]){
    const {card,body}=setup();update(card);appendProposalFeedback(card,body,card._data.proposals[0]);assert.equal(body.children.length,0);card.remove();
  }
});
test("private journal renders literal text, no automatic export/execute, and confirmed own purge",()=>{
  const {card,body}=setup();renderFeedbackJournal(card,body);
  assert.equal(body.querySelector("script"),null);assert.ok(body.textContent.includes("<script>PRIVATE_EXPECTED</script>"));
  assert.equal(body.querySelector("a"),null);assert.equal(card.calls.length,0);
  const form=body.querySelector("form");submit(form);assert.equal(card.calls.length,0);
  form.querySelector("input").checked=true;submit(form);assert.deepEqual(card.calls,[{action:"conversation.feedback_purge",payload:{id:"F000001",confirmed:true}}]);
  card.remove();
});
test("missing source is explicitly unknown and other identity notes never render",()=>{
  const {card,body}=setup();card._data.semantic_feedback.records[0].source_available=false;card._data.semantic_feedback.records[0].source="";
  card._data.semantic_feedback.records.push({...note(),id:"other",actor:"sibling",expected:"SIBLING_PRIVATE_CANARY"});
  renderFeedbackJournal(card,body);assert.ok(body.textContent.includes(FEEDBACK_COPY.en.missing));assert.ok(!body.textContent.includes("SIBLING_PRIVATE_CANARY"));card.remove();
});
test("changed record, account or availability prevents stale purge",()=>{
  for(const change of [c=>c._data.semantic_feedback.records[0].expected="changed",c=>c._data.members[0].revision++,
    c=>c._hass.user={id:"ha-synthetic"},c=>c._data.semantic_feedback.available=false,c=>c.remove()]){
    const {card,body}=setup();renderFeedbackJournal(card,body);const form=body.querySelector("form");form.querySelector("input").checked=true;change(card);submit(form);assert.equal(card.calls.length,0);card.remove();
  }
});
test("unavailable storage has no destructive controls",()=>{
  const {card,body}=setup();card._data.semantic_feedback.available=false;renderFeedbackJournal(card,body);assert.ok(body.textContent.includes(FEEDBACK_COPY.en.unavailable));assert.equal(body.querySelector("form"),null);card.remove();
});
