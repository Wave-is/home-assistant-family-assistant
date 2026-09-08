import assert from "node:assert/strict";
import { test } from "node:test";
import { JSDOM } from "jsdom";
const dom = new JSDOM("<!doctype html><body></body>", {url: "https://example.invalid"});
globalThis.document = dom.window.document;
const {DEVELOPER_COPY, renderDeveloper, reportJSON} = await import(
  "../custom_components/family_assistant/frontend/developer-view.js");
const report = () => ({format:"family_assistant_defect_report", schema:1, version:"0.1.0-alpha.28",
  cases:[{stage:"assistant_job",code:"provider_timeout",has_quote:true,has_refs:false,count:2}],
  overflow_count:0,saturated:false,
  limitations:["technical_observations_only","no_message_content","not_a_semantic_reproducer"]});
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
function setup(role="owner", language="en") {
  const card = document.createElement("div"), body = document.createElement("div");
  card.append(body); document.body.append(card);
  Object.assign(card, {_entry:"synthetic-entry",_generation:1,_config:{language},
    _hass:{user:{id:"synthetic-ha"},callWS:async () => report()},
    _data:{actor:"owner",role,members:[{id:"owner",role,active:true,revision:1}],
      developer_diagnostics:{available:true,enabled:true,generation:2,count:1,saturated:false}}});
  renderDeveloper(card, body);
  return {card,body};
}
test("three languages and owner-only opt-in explanatory UI", () => {
  for (const language of ["en","ru","uk"]) {
    assert.deepEqual(Object.keys(DEVELOPER_COPY[language]).sort(),Object.keys(DEVELOPER_COPY.en).sort());
    const {card,body}=setup("owner",language);
    assert.ok(body.textContent.includes(DEVELOPER_COPY[language].hint));
    card.remove();
  }
  for(const role of ["parent","child","adult","guest"]) {
    const {card,body}=setup(role); assert.equal(body.textContent,""); card.remove();
  }
});
test("strict report schema rejects every private extension and malformed category", () => {
  assert.ok(reportJSON(report()).endsWith("\n"));
  for (const mutate of [r=>r.private="CANARY",r=>r.cases[0].message="CANARY",
    r=>r.cases[0].code="CANARY",r=>r.version+="\n",r=>r.version="0.1.0-alpha",
    r=>r.cases.push({...r.cases[0]}),r=>r.limitations.push("CANARY")]) {
    const r=report(); mutate(r); assert.throws(()=>reportJSON(r));
  }
});
test("preview sends only entry and consent epoch, never exports until explicit fresh download", async () => {
  const {card,body}=setup(), calls=[];
  card._hass.callWS=async request=>{calls.push(request);return report();};
  const oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;
  let exported,revoked=0,downloads=0;
  URL.createObjectURL=blob=>{exported=blob;return "blob:synthetic";};
  URL.revokeObjectURL=()=>{revoked++;};
  const oldClick=dom.window.HTMLAnchorElement.prototype.click;
  dom.window.HTMLAnchorElement.prototype.click=function(){downloads++;assert.equal(this.download,"family-assistant-technical-report.json");};
  try {
    body.querySelector("button").click(); await tick();
    assert.equal(downloads,0); assert.equal(body.querySelector("pre").textContent, reportJSON(report()));
    const download=[...body.querySelectorAll("button")].find(b=>b.textContent===DEVELOPER_COPY.en.download);
    download.click();await tick();await tick();
    assert.equal(downloads,1);assert.equal(revoked,1);
    assert.equal(await exported.text(),reportJSON(report()));
    assert.deepEqual(calls,[0,1].map(()=>({type:"family_assistant/developer_report",entry_id:"synthetic-entry",expected_generation:2})));
  } finally {URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;dom.window.HTMLAnchorElement.prototype.click=oldClick;card.remove();}
});
test("late responses cannot render after access, generation, household or attachment drift", async () => {
  for(const change of [c=>c._data.role="parent",c=>c._data.members[0].revision++,
    c=>c._entry="other",c=>c._generation++,c=>c._data.developer_diagnostics.generation++,
    c=>c._hass.user={id:"synthetic-ha"},c=>c.remove()]) {
    const {card,body}=setup();let resolve;
    card._hass.callWS=()=>new Promise(r=>{resolve=r;});
    body.querySelector("button").click();change(card);resolve(report());await tick();
    assert.equal(body.querySelector("pre"),null);card.remove();
  }
});
test("changed report and raw provider exceptions produce fixed error and no download", async () => {
  for(const mode of ["changed","error","canary"]) {
    const {card,body}=setup();let calls=0;
    card._hass.callWS=async()=>{calls++; const r=report(); if(calls>1) {
      if(mode==="error") throw new Error("PRIVATE_CANARY");
      if(mode==="changed") r.cases[0].count++;
      if(mode==="canary") r.private="PRIVATE_CANARY";
    } return r;};
    body.querySelector("button").click();await tick();
    [...body.querySelectorAll("button")].find(b=>b.textContent===DEVELOPER_COPY.en.download).click();await tick();
    assert.equal(body.querySelector("pre"),null);assert.ok(body.textContent.includes(DEVELOPER_COPY.en.error));
    assert.equal(body.textContent.includes("PRIVATE_CANARY"),false);card.remove();
  }
});
