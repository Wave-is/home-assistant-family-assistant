import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";
import {COURT_COPY,renderCourt} from "../custom_components/family_assistant/frontend/court-view.js";

const dom=new JSDOM("<!doctype html><body></body>");
globalThis.document=dom.window.document;

const example=()=>({id:"example",label:"Example threshold",direction:"at_most",points:-3,members:["child"]});
function fixture({rules=[],role="owner",summary=null,fail=false}={}){
  const body=document.createElement("div"), calls=[];
  const card={
    _generation:1,_config:{language:"en"},_hass:{language:"en"},_courtConfigOpen:role==="owner",
    parent:["owner","parent"].includes(role),_writing:false,_actionError:null,
    _data:{role,actor:role,settings:{timezone:"UTC",modules:["court"]},
      members:[{id:"owner",name:"Owner",role:"owner",active:true},{id:"child",name:"Example child",role:"child",active:true}],
      court:[],court_reports:[],court_summary:summary,court_config:{revision:1,weekday:4,time:"22:00",thresholds:structuredClone(rules)}},
    button(text,action){const button=document.createElement("button");button.type="button";button.textContent=text;button.onclick=action;return button;},
    input(form,name,label,type,value){const wrapper=document.createElement("label"),input=document.createElement("input");wrapper.textContent=label;Object.assign(input,{name,type,value,required:true});wrapper.append(input);form.append(wrapper);return input;},
    async command(action,payload){calls.push({action,payload:structuredClone(payload)});card._actionError=fail?"synthetic_failure":null;},
    render(){body.replaceChildren();renderCourt(card,body);},
  };
  card.render();
  return {card,body,calls};
}
function click(body,label){[...body.querySelectorAll("button")].find(button=>button.textContent===label).click();}
function input(body,name,value,event="input"){
  const element=body.querySelector(`[name="${name}"]`);element.value=value;element.dispatchEvent(new dom.window.Event(event));return element;
}
async function submit(body){body.querySelector("form").dispatchEvent(new dom.window.Event("submit",{cancelable:true}));await Promise.resolve();await Promise.resolve();}

test("threshold editor preserves unedited rules when saving report time",async()=>{
  const {body,calls,card}=fixture({rules:[example()]});
  input(body,"time","21:45");await submit(body);
  assert.equal(calls[0].payload.time,"21:45");
  assert.equal(Object.hasOwn(calls[0].payload,"thresholds"),false);
  assert.deepEqual(card._data.court_config.thresholds,[example()]);
});

test("owner can add a named member threshold with stable retry payload",async()=>{
  const {body,calls,card}=fixture({fail:true});
  click(body,COURT_COPY.en.threshold_add);
  input(body,"threshold_label_0","Example saved rule");
  input(body,"threshold_direction_0","at_least","change");
  input(body,"threshold_points_0","7");
  const member=body.querySelector('[name="threshold_members_0"]');
  member.options[1].selected=true;member.dispatchEvent(new dom.window.Event("change"));
  await submit(body);
  assert.deepEqual(calls[0].payload.thresholds,[{id:"rule-1",label:"Example saved rule",direction:"at_least",points:7,members:["child"]}]);
  assert.ok(body.querySelector('[name="threshold_label_0"]').disabled);
  await submit(body);
  assert.deepEqual(calls[1],calls[0]);
  assert.equal(card._data.court_config.thresholds.length,0);
});

test("threshold deletion explicitly sends empty rules and does not remove score history",async()=>{
  const {body,calls}=fixture({rules:[example()]});
  click(body,COURT_COPY.en.threshold_remove);await submit(body);
  assert.deepEqual(calls[0].payload.thresholds,[]);
  assert.equal(calls[0].action,"court.configure");
});

test("invalid points and stale configuration cannot save edited thresholds",async()=>{
  const {body,calls,card}=fixture({rules:[example()]});
  input(body,"threshold_points_0","");await submit(body);
  assert.equal(calls.length,0);
  assert.ok(body.textContent.includes(COURT_COPY.en.threshold_invalid));
  input(body,"threshold_points_0","8");card._data.court_config.revision=2;await submit(body);
  assert.equal(calls.length,0);
});

test("child sees authorized threshold status as text and cannot configure",()=>{
  const summary={rows:[{member:"child",active_positives:2,active_negatives:0,total:2,reversed_count:0}],thresholds:[{member:"child",label:"<img src=x>",reached:false,remaining:3}]};
  const {body}=fixture({role:"child",summary});
  assert.ok(body.textContent.includes("<img src=x>: Points to threshold: 3"));
  assert.equal(body.querySelectorAll("img, fieldset, form").length,0);
});

test("closed and disabled forms ignore detached threshold inputs",()=>{
  const {card,body}=fixture({rules:[example()]});
  const control=body.querySelector('[name="threshold_label_0"]');
  click(body,COURT_COPY.en.config_close);
  control.value="Detached mutation";control.dispatchEvent(new dom.window.Event("input"));
  assert.equal(card._courtDraft,null);
  assert.equal(card._data.court_config.thresholds[0].label,"Example threshold");
});
