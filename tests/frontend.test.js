import assert from "node:assert/strict";
import {test} from "node:test";
import {JSDOM} from "jsdom";

const dom=new JSDOM("<!doctype html><body></body>",{url:"http://localhost"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","FormData"])
  globalThis[key]=dom.window[key];
const {COPY}=await import("../custom_components/family_assistant/frontend/family-assistant.js");
const {KID_COPY,KID_FIELDS,kidDiff,renderKids}=await import("../custom_components/family_assistant/frontend/network-kids.js");
const base={revision:1,settings:{name:"Demo family",modules:["shopping","tasks","court","alarms"]},actor:"parent",role:"parent",
  members:[{id:"parent",name:"Parent",role:"parent",active:true},{id:"child",name:"Child",role:"child",active:true}],
  tasks:[],shopping:[],court:[],alarms:[],alarm_runs:[]};
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));

for(const language of ["en","ru","uk"])test(`shadow copy has no mutation controls: ${language}`,async()=>{
  for(const {type} of window.customCards){
    const card=document.createElement(type);card.setConfig({entry_id:"shadow",language});
    card.hass={language,callWS:async m=>{assert.equal(m.type,"family_assistant/view");return {...base,role:"owner",read_only:"migration_shadow_read_only",settings:{...base.settings,modules:[]},tasks:[{id:"T000001",title:"<img src=x onerror=alert(1)>"}]};}};
    await tick();
    assert.ok(card.shadowRoot.querySelector(".migration-shadow [role=status]"));
    assert.equal(card.shadowRoot.querySelectorAll("button,input,form,img").length,0);
    assert.ok(card.shadowRoot.textContent.includes("<img src=x onerror=alert(1)>"));
    card.remove();
  }
});

test("all frontend locales have identical keys",()=>{
  for(const locale of Object.values(COPY))assert.deepEqual(Object.keys(locale).sort(),Object.keys(COPY.en).sort());
  for(const locale of Object.values(KID_COPY))assert.deepEqual(Object.keys(locale).sort(),Object.keys(KID_COPY.en).sort());
  for(const locale of Object.values(KID_FIELDS))assert.deepEqual(Object.keys(locale).sort(),Object.keys(KID_FIELDS.en).sort());
});
test("Kid Control preview uses human terms instead of inverted raw disabled flags",()=>{
  assert.equal(kidDiff("disabled",{before:"false",after:"true"},"ru",[]),"Ограничения: Включены → Выключены");
  assert.equal(kidDiff("paused",{before:"false",after:"true"},"uk",[]),"Примусова пауза: Ні → Так");
});
test("shopping names never become HTML",async()=>{
  const card=document.createElement("family-shopping-card");card.setConfig({entry_id:"demo"});
  card.hass={language:"en",callWS:async()=>({...base,shopping:[{id:"S1",name:"<img src=x onerror=alert(1)>",quantity:1,purchased:0,unit:"",status:"approved",revision:1}]})};
  await tick();assert.equal(card.shadowRoot.querySelector("img"),null);
  assert.match(card.shadowRoot.textContent,/<img src=x/);
});
test("child does not get parent approval controls",async()=>{
  const card=document.createElement("family-court-card");card.setConfig({entry_id:"demo"});
  card.hass={language:"uk",callWS:async()=>({...base,role:"child",actor:"child",court:[{id:"C1",member:"child",reason:"Example",points:1,status:"active"}]})};
  await tick();assert.deepEqual([...card.shadowRoot.querySelectorAll("button")].map(b=>b.textContent),["Оскаржити"]);
});
test("unlinked household shows onboarding hint",async()=>{
  const card=document.createElement("family-shopping-card");card.setConfig({});
  card.hass={language:"ru",callWS:async()=>[]};await tick();
  assert.match(card.shadowRoot.textContent,/Нет привязанной семьи/);
});
test("retry reuses the operation ID after uncertain network result",async()=>{
  const calls=[];let fail=true;const card=document.createElement("family-shopping-card");card.setConfig({entry_id:"demo"});
  card.hass={language:"en",callWS:async(msg)=>{
    if(msg.type.endsWith("/execute")){calls.push(msg);if(fail)throw new Error("Disconnected");return {};}
    return base;
  }};await tick();await card.command("shopping.add",{name:"Milk"});fail=false;
  await card.command("shopping.add",{name:"Milk"});
  assert.equal(calls.length,2);assert.equal(calls[0].operation_id,calls[1].operation_id);
});
test("late response from previous household cannot replace current household",async()=>{
  const card=document.createElement("family-shopping-card");let finish;
  card.setConfig({entry_id:"old"});card.hass={language:"en",callWS:message=>message.entry_id==="old"?new Promise(resolve=>{finish=resolve;}):Promise.resolve({...base,settings:{...base.settings,name:"New household"}})};
  card.setConfig({entry_id:"new"});await tick();
  assert.equal(card._data.settings.name,"New household");assert.equal(card._loading,false);
  finish(base);await tick();assert.equal(card._data.settings.name,"New household");
});

test("changing card configuration during an uncertain write does not lock the new household",async()=>{
  const card=document.createElement("family-shopping-card");let fail;
  card.setConfig({entry_id:"old"});
  card.hass={language:"en",callWS:message=>message.type.endsWith("/execute")?new Promise((_,reject)=>{fail=reject;}):Promise.resolve({...base,settings:{...base.settings,name:message.entry_id}})};
  await tick();const pending=card.command("shopping.add",{name:"Old draft"});
  card.setConfig({entry_id:"new"});await tick();
  assert.equal(card._data.settings.name,"new");assert.equal(card._writing,false);
  assert.ok([...card.shadowRoot.querySelectorAll("button")].some(button=>!button.disabled));
  fail({code:"storage_error"});await pending;
  assert.equal(card._data.settings.name,"new");assert.equal(card._actionError,null);
});

test("a pre-command slow refresh cannot suppress readback or overwrite committed state",async()=>{
  const card=document.createElement("family-shopping-card");let finishOld,reads=0;
  card.setConfig({entry_id:"same"});
  const state=structuredClone(base);
  card.hass={language:"en",callWS:message=>{
    if(message.type.endsWith("/execute")){state.revision=2;return Promise.resolve({});}
    reads++;
    if(reads===2)return new Promise(resolve=>{finishOld=()=>resolve({...base,revision:1});});
    return Promise.resolve(structuredClone(state));
  }};await tick();
  const pending=card.refresh();
  await card.command("shopping.add",{name:"Synthetic"});
  assert.equal(card._data.revision,2);assert.equal(reads,3);
  finishOld();await pending;assert.equal(card._data.revision,2);assert.equal(card._loading,false);
});

test("routine HA state updates do not storm an unresolved household picker or failed first read",async()=>{
  for(const scenario of ["multiple","none","error"]){
    const card=document.createElement("family-shopping-card");let calls=0;
    card.setConfig({});
    const hass={language:"en",user:{id:"same"},callWS:async()=>{calls++;if(scenario==="error")throw {code:"storage_error"};return scenario==="none"?[]:[{entry_id:"one",title:"One"},{entry_id:"two",title:"Two"}];}};
    card.hass=hass;await tick();
    for(let index=0;index<5;index++){card.hass={...hass,states:{}};await tick();}
    assert.equal(calls,1,scenario);
    await card.refresh();assert.equal(calls,2,"Explicit refresh is still available");
  }
});

test("old network refresh cannot unlock a new configuration's active write",async()=>{
  const card=document.createElement("family-network-card");let finishOld,finishNew;
  card.setConfig({entry_id:"old"});
  card.hass={language:"en",callWS:message=>{
    if(message.type.endsWith("/network_refresh"))return new Promise(resolve=>{finishOld=resolve;});
    if(message.type.endsWith("/execute"))return new Promise(resolve=>{finishNew=resolve;});
    return Promise.resolve({...base,settings:{...base.settings,modules:[...base.settings.modules,"mikrotik"]},network:{inventory:null}});
  }};await tick();
  [...card.shadowRoot.querySelectorAll("button")].find(button=>button.textContent==="Read router again").click();
  card.setConfig({entry_id:"new",view:"shopping"});await tick();
  const pending=card.command("shopping.add",{name:"New item"});
  finishOld({});await tick();assert.equal(card._writing,true);
  finishNew({});await pending;assert.equal(card._writing,false);
});

test("changing household clears private recurring-shopping drafts",()=>{
  const card=document.createElement("family-shopping-card");
  card.setConfig({entry_id:"old"});
  card._shoppingSeriesFormOpen=true;
  card._shoppingSeriesEditingItem={id:"B1",name:"Private old household"};
  card._shoppingSeriesDraft={name:"Private draft"};
  card._shoppingItemAction={itemId:"Private old item",frozenPayload:{revision:1}};
  card.setConfig({entry_id:"new"});
  assert.equal(card._shoppingSeriesFormOpen,false);
  assert.equal(card._shoppingSeriesEditingItem,null);
  assert.equal(card._shoppingSeriesDraft,null);
  assert.equal(card._shoppingItemAction,null);
  assert.doesNotMatch(card.shadowRoot.textContent,/Private/);
});

test("late command error cannot overwrite the new household's status",async()=>{
  const card=document.createElement("family-shopping-card");let fail;
  card.setConfig({entry_id:"old"});
  card.hass={language:"en",callWS:message=>message.type.endsWith("/execute")?new Promise((_,reject)=>{fail=reject;}):Promise.resolve(base)};
  await tick();
  const inFlight=card.command("shopping.add",{name:"Private old item"});
  card.setConfig({entry_id:"new"});
  card._actionError="new-household-status";
  fail({code:"old-household-error"});await inFlight;
  assert.equal(card._actionError,"new-household-status");
  assert.doesNotMatch(card.shadowRoot.textContent,/Private old item|old-household-error/);
});

test("calendar card and its editor retain the calendar alias",async()=>{
  const card=document.createElement("family-calendar-card");card.setConfig({});
  assert.equal(card._view,"calendar");
  const editor=document.createElement("family-assistant-card-editor");
  editor.setConfig({type:"custom:family-calendar-card"});
  assert.equal(editor.shadowRoot.querySelector('[name="view"]').value,"calendar");
});

test("visual editor uses authorized household names, not manually entered IDs",async()=>{
  const editor=document.createElement("family-assistant-card-editor");
  editor.setConfig({type:"custom:family-alarms-card"});let emitted;
  editor.addEventListener("config-changed",event=>{emitted=event.detail.config;});
  editor.hass={language:"ru",callWS:async()=>[{entry_id:"synthetic",title:"Пример семьи"}]};
  await tick();const household=editor.shadowRoot.querySelector('[name="entry_id"]');
  assert.equal(household.tagName,"SELECT");assert.match(household.textContent,/Пример семьи/);
  assert.equal(editor.shadowRoot.querySelector('[name="view"]').value,"alarms");
  household.value="synthetic";household.dispatchEvent(new dom.window.Event("change"));
  assert.equal(emitted.entry_id,"synthetic");assert.equal(emitted.type,"custom:family-alarms-card");
});

test("Kid Control renders live configured status, handles timezone, and hides MAC addresses",async()=>{
  const dayNames=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  const makeCard=(lang,statusObj,tz="Europe/Kyiv")=>{
    const body=document.createElement("div");
    const card={
      _data:{
        actor:"parent",role:"parent",
        settings:{name:"Demo family",timezone:tz},
        members:[{id:"child",name:"Child",role:"child",active:true}],
        kid_control:{
          can_manage:true,writable:true,observed_at:"2026-09-06T12:00:00Z",plans:[],
          profiles:[{
            member:"child",name:"Child Profile",device_names:["Phone"],
            observed:{disabled:"false",paused:"false",mon:"08:00-22:00",tue:"08:00-22:00",wed:"—",thu:"—",fri:"—",sat:"—",sun:"—"},
            status:statusObj
          }]
        }
      },
      _config:{language:lang},
      _hass:{language:lang},
      t:{dayNames,networkExpired:"Expired"},
      button:(label,handler)=>{const b=document.createElement("button");b.textContent=label;b.onclick=handler;return b;},
      input:(parent,name,label,type,value)=>{const i=document.createElement("input");i.name=name;i.value=value;parent.append(i);return i;},
      command:()=>{}
    };
    renderKids(card,body);
    return body;
  };

  // 1. English rendering with allowed status, remaining minutes, next change, temporary expiry
  const bodyEn=makeCard("en",{
    mode:"schedule",allows:true,next_change_at:"2026-09-07T20:00:00Z",next_allows:false,remaining_minutes:45,
    temporary_until:"2026-09-07T21:00:00Z",temporary_mode:"grant",valid_until:new Date(Date.now()+60000).toISOString(),reason:"fresh"
  });

test("pantry card and its editor retain the pantry alias",async()=>{
  const card=document.createElement("family-pantry-card");card.setConfig({});
  assert.equal(card._view,"pantry");
  const editor=document.createElement("family-assistant-card-editor");
  editor.setConfig({type:"custom:family-pantry-card"});
  assert.equal(editor.shadowRoot.querySelector('[name="view"]').value,"pantry");
});
  assert.match(bodyEn.textContent,/Normal schedule/);
  assert.match(bodyEn.textContent,/Configured access: Allowed/);
  assert.match(bodyEn.textContent,/Remaining: 45 min/);
  assert.match(bodyEn.textContent,/Next blocked:/);
  assert.match(bodyEn.textContent,/Temporary access until:/);
  assert.match(bodyEn.textContent,/Europe\/Kyiv/);
  assert.match(bodyEn.textContent,/Weekly schedule/);
  assert.match(bodyEn.textContent,/Mon: 08:00-22:00/);
  assert.match(bodyEn.textContent,/Devices: Phone/);
  // MAC addresses must not appear
  assert.doesNotMatch(bodyEn.textContent,/02:11:22:33:44:55/);
  assert.doesNotMatch(bodyEn.textContent,/02:11/);

  // 2. Russian rendering
  const bodyRu=makeCard("ru",{
    mode:"schedule",allows:true,next_change_at:"2026-09-07T20:00:00Z",next_allows:false,remaining_minutes:45,
    temporary_until:"2026-09-07T21:00:00Z",temporary_mode:"grant",valid_until:new Date(Date.now()+60000).toISOString(),reason:"fresh"
  });
  assert.match(bodyRu.textContent,/Обычное расписание/);
  assert.match(bodyRu.textContent,/По настройкам: доступ разрешён/);
  assert.match(bodyRu.textContent,/Осталось: 45 мин/);
  assert.match(bodyRu.textContent,/Следующая блокировка:/);
  assert.match(bodyRu.textContent,/Временный доступ до:/);
  assert.match(bodyRu.textContent,/Еженедельное расписание/);
  assert.doesNotMatch(bodyRu.textContent,/02:11/);

  // 3. Ukrainian rendering
  const bodyUk=makeCard("uk",{
    mode:"schedule",allows:true,next_change_at:"2026-09-07T20:00:00Z",next_allows:false,remaining_minutes:45,
    temporary_until:"2026-09-07T21:00:00Z",temporary_mode:"grant",valid_until:new Date(Date.now()+60000).toISOString(),reason:"fresh"
  });
  assert.match(bodyUk.textContent,/Звичайний розклад/);
  assert.match(bodyUk.textContent,/За налаштуваннями: доступ дозволено/);
  assert.match(bodyUk.textContent,/Залишилося: 45 хв/);
  assert.match(bodyUk.textContent,/Наступне блокування:/);
  assert.match(bodyUk.textContent,/Тимчасовий доступ до:/);
  assert.match(bodyUk.textContent,/Щотижневий розклад/);
  assert.doesNotMatch(bodyUk.textContent,/02:11/);

  // 4. Unknown or missing mode renders generic unknown warning and does not claim historical paused/disabled is live
  const bodyUnk=makeCard("en",{mode:"unknown",allows:null});
  assert.match(bodyUnk.textContent,/Status unknown: refresh router data/);
  assert.doesNotMatch(bodyUnk.textContent,/Configured access: Allowed/);
  assert.doesNotMatch(bodyUnk.textContent,/Configured access: Blocked/);
  assert.doesNotMatch(bodyUnk.textContent,/Restrictions disabled/);

  // 5. Invalidation after valid_until: when valid_until <= Date.now(), mode falls back to unknown
  const bodyExpired=makeCard("en",{
    mode:"schedule",allows:true,valid_until:new Date(Date.now()-1000).toISOString()
  });
  assert.match(bodyExpired.textContent,/Status unknown: refresh router data/);
  assert.doesNotMatch(bodyExpired.textContent,/Configured access: Allowed/);

  // 6. Invalid/missing valid_until must be unknown
  const bodyMissingValid=makeCard("en",{mode:"schedule",allows:true});
  assert.match(bodyMissingValid.textContent,/Status unknown: refresh router data/);
  assert.doesNotMatch(bodyMissingValid.textContent,/Configured access: Allowed/);

  const bodyMalformedValid=makeCard("en",{mode:"schedule",allows:true,valid_until:"not-a-date"});
  assert.match(bodyMalformedValid.textContent,/Status unknown: refresh router data/);

  // 7. Invalid mode or non-boolean allows must be unknown
  const bodyBadMode=makeCard("en",{mode:"something_else",allows:true,valid_until:new Date(Date.now()+60000).toISOString()});
  assert.match(bodyBadMode.textContent,/Status unknown: refresh router data/);

  const bodyBadAllows=makeCard("en",{mode:"schedule",allows:"truthy",valid_until:new Date(Date.now()+60000).toISOString()});
  assert.match(bodyBadAllows.textContent,/Status unknown: refresh router data/);

  // 8. Timed pause rendering
  const bodyPaused=makeCard("en",{
    mode:"paused",allows:false,next_change_at:"2026-09-07T12:00:00Z",next_allows:true,remaining_minutes:null,
    temporary_until:"2026-09-07T12:00:00Z",temporary_mode:"timed_pause",valid_until:new Date(Date.now()+60000).toISOString(),reason:"fresh"
  });
  assert.match(bodyPaused.textContent,/Paused/);
  assert.match(bodyPaused.textContent,/Configured access: Blocked/);
  assert.match(bodyPaused.textContent,/Next allowed:/);
  assert.match(bodyPaused.textContent,/Temporary pause until:/);
});
