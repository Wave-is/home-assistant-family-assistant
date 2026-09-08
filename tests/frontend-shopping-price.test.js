import test from "node:test";
import assert from "node:assert/strict";
import {JSDOM} from "jsdom";
import {PRICE_COPY as COPY, parsePrice} from "../custom_components/family_assistant/frontend/shopping-price.js";
import {SHOPPING_ITEM_COPY as ITEMS} from "../custom_components/family_assistant/frontend/shopping-items.js";
const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","Event","FormData"])globalThis[key]=dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function settle(fn){for(let i=0;i<100;i++){if(fn())return;await tick();}assert.fail("Not settled");}
const button=(root,label)=>[...root.querySelectorAll("button")].find(node=>node.textContent===label);
const input=(root,name,value)=>{const node=root.querySelector(`[name="${name}"]`);node.value=value;node.dispatchEvent(new Event("input",{bubbles:true}));return node;};
async function setup(t,language="en"){
  const state={revision:1,actor:"parent",role:"parent",settings:{name:"Synthetic family",modules:["shopping"],timezone:"UTC"},members:[{id:"parent",name:"Parent",role:"parent",active:true,revision:1}],shopping_series:[],shopping:[{id:"S1",name:"Oats",unit:"kg",quantity:3,purchased:0,status:"approved",revision:1,history:[]}]};
  const calls=[],receipts=new Map();let lose=false;
  const card=document.createElement("family-shopping-card");card.setConfig({type:"custom:family-shopping-card",entry_id:"price-test",language});document.body.append(card);t.after(()=>card.remove());
  card.hass={language,user:{id:"ha-parent"},callWS:async message=>{
    if(message.type==="family_assistant/view")return structuredClone(state);
    assert.equal(message.type,"family_assistant/execute");assert.equal(message.action,"shopping.purchase");calls.push(structuredClone(message));
    if(receipts.has(message.operation_id))return structuredClone(receipts.get(message.operation_id));
    const item=state.shopping[0],p=message.payload;assert.equal(p.revision,item.revision);item.purchased+=p.quantity;item.revision++;if(item.purchased===item.quantity)item.status="purchased";
    item.history.push({at:"2026-09-08T12:00:00Z",actor:"parent",action:"purchase",detail:{amount:p.quantity,unit:item.unit,name:item.name,store:"Market",...(p.price?{price:p.price}:{})}});
    receipts.set(message.operation_id,structuredClone(item));if(lose){lose=false;throw {code:"response_lost"};}return structuredClone(item);
  }};await settle(()=>card._data?.actor==="parent");return {card,state,calls,loseResponse(){lose=true;}};
}
function open(card,language="en"){
  button(card.shadowRoot,ITEMS[language].action_partial_purchase).click();
  const form=card.shadowRoot.querySelector(".shopping-price-fields")?.closest("form");
  assert.ok(form,"Purchase price form must be rendered");
  return form;
}
function fill(form){input(form,"quantity","0.5");const checkbox=form.querySelector(".shopping-price-fields input[type=checkbox]");checkbox.checked=true;checkbox.dispatchEvent(new Event("change",{bubbles:true}));input(form,"price_total","12,5000");input(form,"price_currency","uah");}
for(const language of ["en","ru","uk"])test(`${language}: real card opt-in exact total and shared history`,async t=>{
  const {card,calls}=await setup(t,language);const form=open(card,language);assert.ok(form);assert.ok(form.textContent.includes(COPY[language].shared));assert.equal(form.querySelector('[name="price_total"]').disabled,true);fill(form);
  button(form,ITEMS[language].action_submit).click();await settle(()=>calls.length===1&&!card._writing);assert.deepEqual(calls[0].payload,{id:"S1",revision:1,quantity:0.5,unit:"kg",price:{total:"12.5",currency:"UAH"}});
  assert.ok(card.shadowRoot.textContent.includes("12.5 UAH"));assert.equal(card._shoppingItemAction,null);
});
test("committed response loss retains exact operation even if shared pending slot changes",async t=>{
  const {card,calls,loseResponse}=await setup(t);let form=open(card);fill(form);loseResponse();button(form,ITEMS.en.action_submit).click();await settle(()=>!card._writing&&card._actionError==="response_lost");
  form=card.shadowRoot.querySelector(".shopping-price-fields")?.closest("form");assert.equal(form.querySelector('[name="price_total"]').disabled,true);card._pending={id:"unrelated",fingerprint:"unrelated"};button(form,ITEMS.en.action_retry).click();await settle(()=>calls.length===2&&!card._writing);assert.deepEqual(calls[0],calls[1]);assert.equal(card._shoppingItemAction,null);
});
for(const drift of ["actor","module","user","item","detached"])test(`stale price form cannot submit after ${drift}`,async t=>{
  const {card,state,calls}=await setup(t);const form=open(card);fill(form);const stale=button(form,ITEMS.en.action_submit);
  if(drift==="actor")state.members[0].revision++;
  if(drift==="module")state.settings.modules=[];
  if(drift==="item")state.shopping[0].revision++;
  if(drift==="user")card.hass={...card._hass,user:{id:"other"}};
  else if(drift==="detached")card.remove();else await card.refresh();
  stale.dispatchEvent(new Event("click",{bubbles:true}));form.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}));await tick();assert.equal(calls.length,0);
});
test("invalid price cannot become an unpriced purchase",async t=>{const {card,calls}=await setup(t);const form=open(card);fill(form);input(form,"price_total","NaN");button(form,ITEMS.en.action_submit).click();await tick();assert.equal(calls.length,0);assert.ok(form.textContent.includes(COPY.en.invalid));});

test("turning optional price off preserves draft but omits it from purchase",async t=>{
  const {card,calls}=await setup(t);const form=open(card);fill(form);
  const checkbox=form.querySelector('.shopping-price-fields input[type="checkbox"]');checkbox.checked=false;checkbox.dispatchEvent(new Event("change",{bubbles:true}));
  assert.equal(form.querySelector('[name="price_total"]').value,"12,5000");assert.equal(form.querySelector('[name="price_total"]').disabled,true);
  button(form,ITEMS.en.action_submit).click();await settle(()=>calls.length===1&&!card._writing);assert.equal("price" in calls[0].payload,false);
});

test("zero price is an explicit free purchase, not missing data",async t=>{
  const {card,calls}=await setup(t);const form=open(card);fill(form);input(form,"price_total","0");input(form,"price_currency","USD");button(form,ITEMS.en.action_submit).click();
  await settle(()=>calls.length===1&&!card._writing);assert.deepEqual(calls[0].payload.price,{total:"0",currency:"USD"});assert.ok(card.shadowRoot.textContent.includes("0 USD"));
});

test("historical price names are inert text and currencies remain separate",async t=>{
  const {card,state}=await setup(t);const hostile='<img src=x onerror="alert(1)">';
  state.shopping[0].history=[{at:"2026-09-08T12:00:00Z",actor:"parent",action:"purchase",detail:{amount:1,name:hostile,store:hostile,unit:"kg",price:{total:"1",currency:"USD"}}},{at:"2026-09-08T12:01:00Z",actor:"parent",action:"purchase",detail:{amount:1,name:"Oats",unit:"kg",price:{total:"2",currency:"EUR"}}}];
  await card.refresh();assert.equal(card.shadowRoot.querySelector("img"),null);assert.ok(card.shadowRoot.textContent.includes(hostile));assert.ok(card.shadowRoot.textContent.includes("1 USD"));assert.ok(card.shadowRoot.textContent.includes("2 EUR"));
});
test("strict decimal grammar and currency normalization",()=>{
  assert.deepEqual(parsePrice("0.0000","usd"),{total:"0",currency:"USD"});assert.deepEqual(parsePrice("0,0001","EUR"),{total:"0.0001",currency:"EUR"});
  for(const value of ["NaN","1e2","01","+1","1\n","1.0\n","١","１","999999999.0001","1,2,3",1,true,null])assert.equal(parsePrice(value,"UAH"),null);
  for(const value of ["USD\n","UАH","<b>",true,null])assert.equal(parsePrice("1",value),null);
  for(const language of ["ru","uk"])assert.deepEqual(Object.keys(COPY[language]).sort(),Object.keys(COPY.en).sort());
});
