import assert from "node:assert/strict";
import {test, afterEach} from "node:test";
import {readFile} from "node:fs/promises";
import {JSDOM} from "jsdom";

const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","Element","HTMLElement","customElements","CustomEvent","Event","FormData"])globalThis[key]=dom.window[key];
await import("../custom_components/family_assistant/frontend/family-panel.js");
const {PANEL_COPY,PANEL_MODULES}=await import("../custom_components/family_assistant/frontend/panel-copy.js");
const {searchSettings}=await import("../custom_components/family_assistant/frontend/panel-search.js");
const clone=value=>structuredClone(value);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
const deferred=()=>{let resolve,reject;const promise=new Promise((res,rej)=>{resolve=res;reject=rej;});return {promise,resolve,reject};};
function projection(overrides={}) {
  const members=[{id:"M1",name:"Example Owner",role:"owner",active:true,revision:2,language:"en",ha_user_id:"fixture-owner",aliases:["Owner"],telegram_linked:true},{id:"M2",name:"Example Child",role:"child",active:true,revision:3,language:"uk",aliases:[],telegram_linked:false}];
  return {view:{role:"owner",actor:"M1",members:clone(members),settings:{name:"Example Family",language:"en",timezone:"UTC",modules:["tasks","school","court"],automatic_penalties:false,daily_penalty_cap:0,school_preparation_reminders:false,school_preparation_days_before:0,school_preparation_time:"08:00"}},members,settings_revision:1,onboarding:{revision:1,step:1,completed:false,skipped:[]},connections:{telegram:{configured:true,bot_connected:true,bot_username:"example_test_bot",group_ok:false,send_ok:null,commands_ok:null,text_ok:null},conversation:{configured:false}},capabilities:PANEL_MODULES.map(([id])=>({id,enabled:["tasks","school","court"].includes(id),ready:id==="tasks"||id==="court",issues:id==="school"?["not_configured"]:[]})),...overrides};
}
async function panel({data=projection(),entries=[{entry_id:"example",title:"Example Family"}],handler,language="en"}={}) {
  const calls=[];
  const control=document.createElement("family-assistant-panel");
  let state=clone(data);
  const hass={user:{id:"fixture-owner"},connection:{},language,config:{time_zone:"UTC"},callWS:async message=>{
    calls.push(clone(message));if(handler){const result=await handler(message,state);if(result!==undefined)return result;}
    if(message.type==="family_assistant/households")return clone(entries);
    if(message.type==="family_assistant/panel")return clone(state);
    if(message.type==="family_assistant/execute"){
      if(message.action==="settings.patch"){assert.equal(message.payload.revision,state.settings_revision);Object.assign(state.view.settings,message.payload.changes);state.settings_revision++;return clone(state.view.settings);}
      if(message.action==="members.save"){
        const saved={...message.payload,id:message.payload.id||"M3",revision:(message.payload.revision||0)+1};const i=state.members.findIndex(m=>m.id===saved.id);if(i<0)state.members.push(saved);else state.members[i]={...state.members[i],...saved};state.view.members=clone(state.members);return saved;
      }
      if(message.action==="settings.onboarding"){assert.equal(message.payload.revision,state.onboarding.revision);state.onboarding={...message.payload,revision:state.onboarding.revision+1};return state.onboarding;}
    }
    throw new Error(`Unexpected endpoint ${message.type}`);
  }};
  control.hass=hass;document.body.append(control);await tick();return {control,calls,hass,state,replace:data=>{state=clone(data);}};
}
afterEach(()=>{document.body.replaceChildren();window.confirm=()=>true;});
function input(control,name,value) {const node=control.shadowRoot.querySelector(`[name="${name}"]`);assert.ok(node,`Missing ${name}`);if(node.type==="checkbox")node.checked=value;else node.value=value;node.dispatchEvent(new Event(node.tagName==="SELECT"||node.type==="checkbox"?"change":"input",{bubbles:true}));return node;}
function action(control,id){const button=control.shadowRoot.querySelector(`#${id}`);assert.ok(button,`Missing ${id}`);button.click();}

test("initial state contains no household samples and shows actual loading",async()=>{
  const pending=deferred(),{control}=await panel({handler:m=>m.type==="family_assistant/households"?pending.promise:undefined});
  assert.match(control.shadowRoot.textContent,/Loading your family/);assert.doesNotMatch(control.shadowRoot.textContent,/Example Owner/);
  pending.resolve([]);await tick();assert.match(control.shadowRoot.textContent,/No linked family/);
});
test("failed first read displays an error, never a populated demonstration",async()=>{
  const {control}=await panel({handler:()=>{throw {code:"not_ready"};}});
  assert.ok(control.shadowRoot.querySelector('[role="alert"]'));assert.equal(control.members.length,0);
});
test("multiple households require an explicit selection",async()=>{
  const {control,calls}=await panel({entries:[{entry_id:"first",title:"One"},{entry_id:"second",title:"Two"}]});
  assert.equal(calls.filter(c=>c.type==="family_assistant/panel").length,0);
  await control.selectFamily("second");assert.equal(calls.at(-1).entry_id,"second");assert.equal(control._entry,"second");
});
test("a response from a prior household cannot replace selected family",async()=>{
  const pending=deferred();const {control}=await panel({entries:[{entry_id:"one",title:"One"},{entry_id:"two",title:"Two"}],handler:m=>m.entry_id==="one"?pending.promise:undefined});
  const first=control.selectFamily("one");await tick();await control.selectFamily("two");
  pending.resolve(projection({members:[{id:"old",name:"Old secret"}]}));await first;
  assert.equal(control._entry,"two");assert.doesNotMatch(control.shadowRoot.textContent,/Old secret/);
});
test("member aliases and names are inert text, including attribute payloads",async()=>{
  const data=projection();data.members[0].name='<img src=x onerror="alert(1)">';data.members[0].aliases=['"><script>alert(2)</script>'];
  const {control}=await panel({data});assert.equal(control.shadowRoot.querySelector("img,script"),null);
  control.openMemberView(control.members[0]);assert.equal(control.shadowRoot.querySelector('[name="name"]').value,data.members[0].name);
  assert.equal(control.shadowRoot.querySelector("img,script"),null);
});
test("member creation submits the canonical plural action and server-generated ID",async()=>{
  const {control,calls}=await panel();control.openMemberView(null);input(control,"name","Example Adult");input(control,"role","adult");action(control,"save-member");await tick();
  const write=calls.find(c=>c.type==="family_assistant/execute");assert.equal(write.action,"members.save");assert.equal(write.payload.role,"adult");assert.equal("id"in write.payload,false);assert.equal("revision"in write.payload,false);assert.equal(write.payload.ha_user_id,null);assert.ok(write.operation_id);assert.match(control.shadowRoot.textContent,/Saved and verified/);
});
test("member tab switching preserves unsaved name, role and aliases",async()=>{
  const {control,calls}=await panel();control.openMemberView(control.members[1]);input(control,"name","Edited Child");input(control,"aliasesText","Nickname, Another");
  control._memberTab="advanced";control.render();input(control,"birth_date","2011-06-15");input(control,"avatar","star");action(control,"save-member");await tick();
  const write=calls.find(c=>c.type==="family_assistant/execute");assert.equal(write.payload.name,"Edited Child");assert.equal(write.payload.revision,3);assert.deepEqual(write.payload.aliases,["Nickname","Another"]);assert.equal(write.payload.birth_date,"2011-06-15");assert.equal(write.payload.avatar,"star");
});
test("last-owner rejection preserves current account and draft",async()=>{
  const {control}=await panel({handler:m=>{if(m.type==="family_assistant/execute")throw {code:"last_owner"};}});
  control.openMemberView(control.members[0]);input(control,"role","child");action(control,"save-member");await tick();assert.equal(control.members[0].role,"owner");assert.equal(control._draft.role,"child");assert.ok(control.shadowRoot.querySelector('[role="alert"]'));assert.doesNotMatch(control.shadowRoot.textContent,/Saved and verified/);
});
test("connection failure retries exactly the frozen write and operation ID",async()=>{
  let failed=false;const {control,calls}=await panel({handler:m=>{if(m.type==="family_assistant/execute"&&!failed){failed=true;throw {code:"connection_lost"};}}});
  control.openMemberView(control.members[1]);input(control,"name","New Child Name");action(control,"save-member");await tick();assert.equal(control.shadowRoot.querySelector('[name="name"]').disabled,true);
  action(control,"save-member");await tick();const writes=calls.filter(c=>c.type==="family_assistant/execute");assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);assert.equal(control.members[1].name,"New Child Name");
});
test("a save with failed verification never shows success",async()=>{
  let wrote=false;const {control}=await panel({handler:m=>{if(m.type==="family_assistant/execute")wrote=true;if(m.type==="family_assistant/panel"&&wrote)throw {code:"connection_lost"};}});
  control.openMemberView(control.members[1]);input(control,"name","Verify Me");action(control,"save-member");await tick();assert.match(control.shadowRoot.textContent,/verification failed/);assert.doesNotMatch(control.shadowRoot.textContent,/Saved and verified/);assert.ok(control._pending);
});
test("a stale member projection after acceptance cannot claim verified save",async()=>{
  const before=projection();let wrote=false;
  const {control}=await panel({handler:m=>{if(m.type==="family_assistant/execute")wrote=true;if(m.type==="family_assistant/panel"&&wrote)return clone(before);}});
  control.openMemberView(control.members[1]);input(control,"name","Changed but unverified");action(control,"save-member");await tick();assert.match(control.shadowRoot.textContent,/verification failed/);assert.doesNotMatch(control.shadowRoot.textContent,/Saved and verified/);
});
test("school settings preserve same-day zero and only patch that section",async()=>{
  const {control,calls}=await panel();control.openModuleView("school");input(control,"school_preparation_reminders",true);input(control,"school_preparation_days_before","0");input(control,"school_preparation_time","17:30");action(control,"save-settings");await tick();
  const write=calls.find(c=>c.type==="family_assistant/execute");assert.equal(write.action,"settings.patch");assert.deepEqual(write.payload,{revision:1,changes:{school_preparation_reminders:true,school_preparation_days_before:0,school_preparation_time:"17:30"}});assert.equal(control.settings.automatic_penalties,false);
});
test("failed module toggle never changes live enabled state",async()=>{
  const {control}=await panel({handler:m=>{if(m.type==="family_assistant/execute")throw {code:"conflict"};}});
  await control.toggleModule("pantry",true);assert.equal(control.settings.modules.includes("pantry"),false);assert.match(control.shadowRoot.textContent,/another window/);
});
test("capability disabling writes only the exact modules list",async()=>{
  const {control,calls}=await panel();await control.toggleModule("school",false);const write=calls.find(c=>c.type==="family_assistant/execute");assert.deepEqual(write.payload,{revision:1,changes:{modules:["court","tasks"]}});assert.equal(control.settings.school_preparation_time,"08:00");
});
test("dirty navigation requires an explicit discard and preserves text when cancelled",async()=>{
  window.confirm=()=>false;const {control}=await panel();control.openMemberView(control.members[1]);input(control,"name","Unsaved");control.setTab("modules");assert.equal(control._tab,"members");assert.equal(control._draft.name,"Unsaved");
  window.confirm=()=>true;control.setTab("modules");assert.equal(control._tab,"modules");assert.equal(control._draft,null);
});
test("owner role revocation clears private profile data and disables writes",async()=>{
  const {control,replace}=await panel();control.openMemberView(control.members[1]);input(control,"aliasesText","Private draft");const changed=projection();changed.view.role="child";changed.members=[{id:"M2",name:"Example Child",role:"child"}];replace(changed);await control.loadData();
  assert.equal(control._draft,null);assert.equal(control.owner,false);assert.equal(control.shadowRoot.querySelector("#add-member"),null);assert.doesNotMatch(control.shadowRoot.textContent,/Private draft/);
});
test("a new HA identity cannot see the previous family while its read is pending",async()=>{
  const {control,hass}=await panel();const pending=deferred();control.hass={...hass,user:{id:"other-user"},callWS:()=>pending.promise};assert.equal(control._data,null);assert.doesNotMatch(control.shadowRoot.textContent,/Example Owner/);pending.resolve([]);await tick();
});
test("child and parent do not receive member-management save controls",async()=>{
  for(const role of ["child","parent","guest"]){const data=projection();data.view.role=role;const {control}=await panel({data});control.openMemberView(control.members[1]);assert.equal(control.shadowRoot.querySelector("#save-member"),null);assert.equal(await control.command("members.save",{}),false);control.remove();}
});
test("onboarding resumes from server and finishing persists without module mutations",async()=>{
  const data=projection({onboarding:{revision:5,step:3,completed:false,skipped:["telegram"]}});const {control,calls}=await panel({data});action(control,"setup-guide");assert.equal(control.shadowRoot.querySelector('[aria-current="step"]').textContent,"3. Capabilities");await control.wizardStep(4);await control.wizardStep(4,{completed:true});
  const writes=calls.filter(c=>c.type==="family_assistant/execute");assert.deepEqual(writes.map(m=>m.action),["settings.onboarding","settings.onboarding"]);assert.equal(writes[1].payload.revision,6);assert.equal(control._data.onboarding.completed,true);assert.equal(control._wizardOpen,false);
});
test("wizard member action actually opens the editable profile",async()=>{
  const {control}=await panel();action(control,"setup-guide");action(control,"add-member");assert.ok(control.shadowRoot.querySelector("#member-form"));assert.equal(control._wizardOpen,false);
});
test("Telegram transport configuration never proves sending or text reception",async()=>{
  const {control}=await panel();control.setTab("connections");assert.equal(control.shadowRoot.querySelectorAll(".panel-status-row strong")[1].textContent,"Not checked");assert.match(control.shadowRoot.textContent,/Ordinary text receptionNot checked/);assert.match(control.shadowRoot.textContent,/Example OwnerLinked/);
});
test("an invitation failure never invents a bot, code or success",async()=>{
  const {control}=await panel({handler:m=>{if(m.type==="family_assistant/telegram_invite")throw {code:"telegram_unavailable"};}});await control.generateTelegramInvite("M2");assert.equal(control._invite,null);assert.equal(control.shadowRoot.querySelector('[role="dialog"]'),null);
});
test("Telegram enrollment is confirmed only after explicit review of exact candidate",async()=>{
  const record={id:"example-enrollment",kind:"member",member:"M2",state:"captured",expires_at:"2030-01-01T00:00:00Z",candidate:{name:"Example Child",username:"synthetic_account",chat_id:987654321,user_id:987654321}};
  const {control,calls}=await panel({handler:m=>{
    if(m.type==="family_assistant/telegram_enrollment")return clone(record);
    if(m.type==="family_assistant/telegram_enrollment_confirm"){record.state="confirmed";return {linked:true};}
  }});
  await control.openEnrollment(record);assert.equal(control.shadowRoot.querySelector("#confirm-enrollment").disabled,true);await control.confirmEnrollment();assert.equal(calls.filter(m=>m.type.endsWith("enrollment_confirm")).length,0);
  const check=control.shadowRoot.querySelector('[name="confirm_account"]');check.checked=true;check.dispatchEvent(new Event("change"));await control.confirmEnrollment();
  const sent=calls.find(m=>m.type.endsWith("enrollment_confirm"));assert.deepEqual(sent.candidate,{chat_id:987654321,user_id:987654321});assert.equal(sent.enrollment_id,"example-enrollment");assert.equal(control._invite.state,"confirmed");assert.match(control.shadowRoot.textContent,/Link confirmed/);
});
test("status refresh revokes prior candidate consent and safely renders account names",async()=>{
  const record={id:"example-enrollment",kind:"member",member:"M2",state:"captured",expires_at:"2030-01-01T00:00:00Z",candidate:{name:'<img src=x onerror="alert(1)">',username:"synthetic",chat_id:123456789,user_id:123456789}};
  const {control}=await panel({handler:m=>m.type==="family_assistant/telegram_enrollment"?clone(record):undefined});await control.openEnrollment(record);input(control,"confirm_account",true);assert.ok(control._enrollmentConsent);await control.refreshEnrollment();assert.equal(control._enrollmentConsent,null);assert.equal(control.shadowRoot.querySelector("#confirm-enrollment").disabled,true);assert.equal(control.shadowRoot.querySelector("img"),null);
});
test("expired Telegram enrollments cannot be confirmed",async()=>{
  const record={id:"expired",kind:"member",member:"M2",state:"captured",expires_at:"2000-01-01T00:00:00Z",candidate:{name:"Example",chat_id:123456789,user_id:123456789}};
  const {control,calls}=await panel();control._invite=record;control._enrollmentConsent=control.enrollmentFingerprint(record);control.render();assert.equal(control.shadowRoot.querySelector("#confirm-enrollment"),null);await control.confirmEnrollment();assert.equal(calls.filter(m=>m.type.endsWith("enrollment_confirm")).length,0);assert.match(control.shadowRoot.textContent,/Invitation expired/);
});
test("group invitation uses its actual addressed command and no member ID",async()=>{
  const {control,calls}=await panel({handler:m=>m.type==="family_assistant/telegram_invite"?{id:"group-enrollment",code:"SYNTHETICCODE1234",instruction:"/family_setup@example_test_bot SYNTHETICCODE1234",bot_username:"example_test_bot",expires_at:"2030-01-01T00:00:00Z"}:undefined});
  await control.generateTelegramInvite(null,"group");const sent=calls.find(m=>m.type==="family_assistant/telegram_invite");assert.equal(sent.kind,"group");assert.equal("member_id"in sent,false);assert.equal(control.shadowRoot.querySelector('[role="dialog"] input').value,"/family_setup@example_test_bot SYNTHETICCODE1234");assert.equal(control._invite.kind,"group");
});
test("pending enrollment metadata resumes a confirmation without storing its secret code",async()=>{
  const record={id:"pending-enrollment",kind:"member",member:"M2",state:"issued",expires_at:"2030-01-01T00:00:00Z"};const data=projection({enrollments:[record]});
  const {control}=await panel({data,handler:m=>m.type==="family_assistant/telegram_enrollment"?record:undefined});control.setTab("connections");assert.match(control.shadowRoot.textContent,/Pending invitations/);await control.openEnrollment(record);assert.match(control.shadowRoot.querySelector('[role="dialog"]').textContent,/link was lost/);assert.equal(control._invite.code,undefined);
});
test("recognition preview uses only the nonexecuting endpoint",async()=>{
  const {control,calls}=await panel({handler:m=>m.type==="family_assistant/ai_sandbox_test"?{recognized:true,simulated:true,intent:"court.award",payload:{assessments:[{member:"M2",points:1,reason:"helped"}]}}:undefined});
  control.setTab("connections");input(control,"phrase","Example Child helped");const button=[...control.shadowRoot.querySelectorAll("button")].find(b=>b.textContent==="Preview without executing");button.click();await tick();assert.equal(calls.filter(c=>c.type==="family_assistant/execute").length,0);assert.match(control.shadowRoot.textContent,/Example Child: \+1/);
});
test("all locales have full copy and settings search uses localized paths",()=>{
  for(const lang of ["en","ru","uk"]){assert.deepEqual(Object.keys(PANEL_COPY[lang]).sort(),Object.keys(PANEL_COPY.en).sort());assert.ok(Object.values(PANEL_COPY[lang]).every(Boolean));}
  assert.equal(searchSettings("штраф","ru")[0].moduleId,"court");assert.equal(searchSettings("баллы","ru")[0].title,"Баллы и правила");assert.equal(searchSettings("бали","uk")[0].title,"Бали й правила");assert.equal(searchSettings("points","en")[0].section,"modules");
});
test("duplicate module loading keeps existing registrations and card catalog intact",async()=>{
  await import("../custom_components/family_assistant/frontend/family-assistant.js?panel-first");const initial=window.customCards.length,cardClass=customElements.get("family-assistant-card");
  await import("../custom_components/family_assistant/frontend/family-assistant.js?panel-second");assert.equal(window.customCards.length,initial);assert.equal(customElements.get("family-assistant-card"),cardClass);
});
test("runtime source has no interpolation sink or fabricated success/sample identities",async()=>{
  const source=await readFile(new URL("../custom_components/family_assistant/frontend/family-panel.js",import.meta.url),"utf8");assert.doesNotMatch(source,/innerHTML|telegram_id:\s*\d|FamilyAssistantBot|192\.168\./);
});

test("overview and profile show actual per-child gaps and never mark disabled alarms configured",async()=>{
  for(const language of ["en","ru","uk"]){
    const data=projection();data.view.settings.modules.push("alarms");data.member_readiness=[{id:"M2",alarms:{total:2,enabled:0,strict:1,output_configured:false,issues:["alarm_schedules_disabled","alarm_output_missing"]},school:{timetables:0,issues:["school_no_timetable"]}}];
    const {control}=await panel({data,language});
    for(const code of ["alarm_schedules_disabled","alarm_output_missing","school_no_timetable"])assert.ok(control.shadowRoot.textContent.includes(PANEL_COPY[language][`reason_${code}`]));
    control.openMemberView(control.members[1]);const readiness=control.shadowRoot.querySelector(".panel-member-readiness");assert.equal(readiness.querySelectorAll(".panel-status-row strong").length,2);
    assert.ok([...readiness.querySelectorAll(".panel-status-row strong")].every(item=>item.textContent===PANEL_COPY[language].configure));control.remove();
  }
});

test("missing member readiness and unverified runtime stay unknown instead of green",async()=>{
  const data=projection();data.view.settings.modules.push("alarms");data.capabilities.find(item=>item.id==="school").ready=null;
  const {control}=await panel({data});control.openModuleView("school");assert.ok([...control.shadowRoot.querySelectorAll(".panel-status-row strong")].some(item=>item.textContent===PANEL_COPY.en.unknown));
  control.openMemberView(control.members[1]);assert.ok([...control.shadowRoot.querySelectorAll(".panel-member-readiness .panel-status-row strong")].every(item=>item.textContent===PANEL_COPY.en.unknown));
});

test("member workspace config retains selected ID and reminder section, global navigation clears it",async()=>{
  const data=projection();const {control}=await panel({data,handler:message=>message.type==="family_assistant/view"?{...clone(data.view),school:{timetables:[],homework:[],upcoming:[],preparations:[]}}:undefined});
  control.openMemberWorkspace(control.members[1],"school","reminders");await tick();const card=control.shadowRoot.querySelector("family-assistant-card");assert.equal(card._config.member_id,"M2");assert.equal(card._config.school_section,"reminders");assert.match(control.shadowRoot.textContent,/Settings for: Example Child/);assert.equal(control.shadowRoot.querySelector("#save-settings"),null);
  control.openModuleView("school",true);await tick();assert.equal(control.shadowRoot.querySelector("family-assistant-card")._config.member_id,undefined);assert.equal(control._workspaceMember,null);
});
