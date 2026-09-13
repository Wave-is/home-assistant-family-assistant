import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";
import {SETTLEMENT_COPY,defaultMissedPolicy,settlementSupported,settlementControls} from "../custom_components/family_assistant/frontend/task-settlements.js";

test("default policy requires separate opt-in for all three effects",() => {
  assert.deepEqual(defaultMissedPolicy(),{daily_rollover:false,settle_time:"20:00",repeat_penalty:false,same_day_correction:false});
  const changed=defaultMissedPolicy(); changed.daily_rollover=true;
  assert.equal(defaultMissedPolicy().daily_rollover,false);
});

test("settlement copy has complete EN/RU/UK parity",() => {
  for (const language of ["en","ru","uk"]) {
    assert.deepEqual(Object.keys(SETTLEMENT_COPY[language]).sort(),Object.keys(SETTLEMENT_COPY.en).sort());
    assert.ok(Object.values(SETTLEMENT_COPY[language]).every(value => typeof value === "string" && value.trim()));
    assert.match(SETTLEMENT_COPY[language].settlement_capacity,/366/);
  }
});

test("UI settlement eligibility excludes private and materialized work and nonparents",() => {
  const card={parent:true,_data:{members:[{id:"child",active:true,role:"child"}]}};
  assert.equal(settlementSupported(card,{assignee:"child"}),true);
  for (const extra of [{delivery_scope:"personal"},{delivery_scope:"private"},{source:{kind:"school_homework"}},{series_id:"TS000001"},{occurrence_id:"O000001"},{managed_by:"school"}]) {
    assert.equal(settlementSupported(card,{assignee:"child",...extra}),false);
  }
  assert.equal(settlementSupported({...card,parent:false},{assignee:"child"}),false);
  assert.equal(settlementSupported(card,{assignee:"adult"}),false);
});

for (const language of ["en","ru","uk"]) test(`dependent controls reset consent, preserve local cutoff and disable unsupported scope (${language})`,() => {
  const dom=new JSDOM("<!doctype html><body></body>"), document=dom.window.document;
  const el=(tag,text) => {const node=document.createElement(tag); if(text) node.textContent=text; return node;};
  const container=el("form"), changes=[];
  const controls=settlementControls({_config:{language}},el,container,{daily_rollover:true,settle_time:"00:00",repeat_penalty:true,same_day_correction:true},value=>changes.push(value));
  const input=name=>container.elements.namedItem(`missed_${name}`);
  assert.equal(input("settle_time").value,"00:00");
  input("daily_rollover").checked=false;
  input("daily_rollover").dispatchEvent(new dom.window.Event("change"));
  assert.deepEqual(changes[0],{daily_rollover:false,settle_time:"00:00",repeat_penalty:false,same_day_correction:false});
  assert.equal(input("repeat_penalty").disabled,true);
  input("daily_rollover").checked=true;
  input("daily_rollover").dispatchEvent(new dom.window.Event("change"));
  assert.equal(input("same_day_correction").checked,false);
  controls.available(false);
  assert.equal(controls.fieldset.disabled,true);
  input("daily_rollover").dispatchEvent(new dom.window.Event("change"));
  assert.equal(changes.length,2);
});
