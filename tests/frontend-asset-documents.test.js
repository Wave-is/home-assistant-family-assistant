import test from "node:test";
import assert from "node:assert/strict";
import {JSDOM} from "jsdom";
import {DOCUMENT_COPY as COPY} from "../custom_components/family_assistant/frontend/asset-document-copy.js";
const dom=new JSDOM("<!doctype html><body></body>",{url:"https://example.invalid"});
for(const key of ["window","document","HTMLElement","customElements","CustomEvent","Event","FormData"])globalThis[key]=dom.window[key];
await import("../custom_components/family_assistant/frontend/family-assistant.js");
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
async function settle(check){for(let i=0;i<100;i++){if(check())return;await tick();}assert.fail("Not settled");}
const button=(root,label)=>[...root.querySelectorAll("button")].find(b=>b.textContent===label);
const field=(form,name,value)=>{const input=form.querySelector(`[name="${name}"]`);input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));return input;};
const form=card=>card.shadowRoot.querySelector("[data-document-form]");
async function setup(t,language="en"){
  const state={revision:1,actor:"owner",role:"owner",settings:{name:"Synthetic family",modules:["maintenance"],timezone:"UTC"},members:[{id:"owner",name:"Owner",role:"owner",active:true,revision:1}],maintenance:{assets:[{id:"MX1",revision:1,name:"Synthetic cleaner",category:"Appliance",location:"Lab",status:"active",current:true,can_report:false,warranty:{expires_on:null,vendor:"",reference:""},consumables:[],note:"",history:[]}],documents:[],faults:[],services:[],service_logs:[]}};
  const calls=[],http=[],receipts=new Map(),revoked=[];let lose=false;
  const oldCreate=URL.createObjectURL,oldRevoke=URL.revokeObjectURL;
  URL.createObjectURL=()=>"blob:synthetic-document";URL.revokeObjectURL=url=>revoked.push(url);t.after(()=>{URL.createObjectURL=oldCreate;URL.revokeObjectURL=oldRevoke;});
  const card=document.createElement("family-maintenance-card");card.setConfig({type:"custom:family-maintenance-card",entry_id:"documents-test",language});document.body.append(card);t.after(()=>card.remove());
  card.hass={language,user:{id:"ha-owner"},callWS:async message=>{
    if(message.type==="family_assistant/view")return structuredClone(state);
    calls.push(structuredClone(message));if(receipts.has(message.operation_id))return structuredClone(receipts.get(message.operation_id));let result;
    if(message.action==="media.reserve")result={id:"M1",revision:1,status:"reserved"};
    else if(message.action==="maintenance.document_attach"){
      const p=message.payload;assert.equal(p.id,"MX1");assert.deepEqual(p.media,{id:"M1",revision:2});
      state.maintenance.documents.push({id:"MD1",revision:1,asset_id:p.id,title:p.title,kind:p.kind,note:p.note,status:"attached",attachment:{id:"M1",revision:3,purpose:"equipment_document",status:"attached",size_bytes:13,mime_type:"application/pdf"}});
      result={id:"MD1",revision:1,asset_id:"MX1",status:"attached"};
    }else if(message.action==="maintenance.document_purge"){
      assert.equal(message.payload.document.id,"MD1");const row=state.maintenance.documents[0];row.revision++;row.status="deleted";delete row.attachment;result={id:"MD1",revision:2,asset_id:"MX1",status:"deleted"};
    }else assert.fail(message.action);
    receipts.set(message.operation_id,structuredClone(result));if(lose&&message.action!=="media.reserve"){lose=false;throw {code:"storage_error"};}return result;
  },fetchWithAuth:async(path,options)=>{
    http.push({path,method:options.method,type:options.headers["Content-Type"]});
    if(options.method==="PUT")return new Response(JSON.stringify({id:"M1",revision:2,status:"available"}),{headers:{"content-type":"application/json"}});
    return new Response("synthetic pdf",{headers:{"content-type":"application/pdf","content-length":"13"}});
  }};await settle(()=>card._data?.actor==="owner");return{card,state,calls,http,revoked,loseResponse(){lose=true;}};
}
function draft(card,language="en"){
  button(card.shadowRoot,COPY[language].add).click();let f=form(card);assert.ok(f);
  const file=new Blob(["synthetic pdf"],{type:"application/pdf"});Object.defineProperty(file,"name",{value:"synthetic.pdf"});
  const input=f.querySelector('[type="file"]');Object.defineProperty(input,"files",{value:[file]});input.dispatchEvent(new Event("change",{bubbles:true}));
  f=form(card);field(f,"title","Synthetic warranty");field(f,"note","<img src=x onerror=alert(1)>");return f;
}
async function uploaded(card,language="en"){draft(card,language);button(form(card),COPY[language].upload).click();await settle(()=>card._assetDocumentDraft?.available&&!card._writing);}
for(const language of ["en","ru","uk"])test(`${language}: real card private upload, separate attachment, no automatic file reads`,async t=>{
  const{card,calls,http}=await setup(t,language);assert.equal(http.length,0);await uploaded(card,language);assert.equal(calls.length,1);assert.equal(calls[0].action,"media.reserve");assert.equal(http.length,1);assert.ok(form(card).textContent.includes(COPY[language].privacy)===false);assert.ok(card.shadowRoot.textContent.includes(COPY[language].privacy));
  button(form(card),COPY[language].attach).click();await settle(()=>calls.length===2&&!card._writing);assert.equal(form(card),null);assert.equal(calls[1].payload.title,"Synthetic warranty");assert.equal(http.length,1);assert.equal(card.shadowRoot.querySelector("img,iframe,embed,object"),null);assert.ok(card.shadowRoot.textContent.includes("<img src=x onerror=alert(1)>"));
});
test("lost attach response reuses frozen payload and operation ID",async t=>{
  const{card,calls,loseResponse,state}=await setup(t);await uploaded(card);loseResponse();button(form(card),COPY.en.attach).click();await settle(()=>!card._writing&&card._actionError==="storage_error");const first=structuredClone(calls[1]);assert.equal(form(card).querySelector('[name="title"]').disabled,true);card._pending={id:"unrelated",fingerprint:"other"};button(form(card),COPY.en.retry).click();await settle(()=>calls.length===3&&!card._writing);assert.deepEqual(calls[2],first);assert.equal(state.maintenance.documents.length,1);
});
test("owner purge is reviewed and exact replay survives committed projection",async t=>{
  const{card,calls,loseResponse}=await setup(t);await uploaded(card);button(form(card),COPY.en.attach).click();await settle(()=>!card._writing&&!form(card));button(card.shadowRoot,COPY.en.purge).click();assert.ok(form(card).textContent.includes(COPY.en.purge_warning));field(form(card),"reason","Synthetic explicit review");loseResponse();button(form(card),COPY.en.confirm_purge).click();await settle(()=>!card._writing&&card._actionError==="storage_error");const first=structuredClone(calls.at(-1));button(form(card),COPY.en.retry).click();await settle(()=>!card._writing&&!form(card));assert.deepEqual(calls.at(-1),first);assert.ok(card.shadowRoot.textContent.includes(COPY.en.deleted));
});
for(const drift of ["member","role","module","asset","user","entry","detached"])test(`revoked ${drift} draft cannot submit`,async t=>{
  const{card,calls,state}=await setup(t);const stale=draft(card),submit=button(stale,COPY.en.upload);
  if(drift==="member")state.members[0].revision++;
  if(drift==="role"){state.members[0].role="child";state.role="child";}
  if(drift==="module")state.settings.modules=[];
  if(drift==="asset")state.maintenance.assets[0].revision++;
  if(drift==="user")card.hass={...card._hass,user:{id:"other"}};
  else if(drift==="entry")card.setConfig({type:"custom:family-maintenance-card",entry_id:"other"});
  else if(drift==="detached")card.remove();else await card.refresh();
  submit.dispatchEvent(new Event("click",{bubbles:true}));stale.dispatchEvent(new Event("submit",{bubbles:true,cancelable:true}));await tick();assert.equal(calls.length,0);
});
test("download is explicit, attachment-only and revoked with current identity",async t=>{
  const{card,http,state,revoked}=await setup(t);await uploaded(card);button(form(card),COPY.en.attach).click();await settle(()=>!card._writing&&!form(card));assert.equal(http.filter(x=>x.method==="GET").length,0);button(card.shadowRoot,COPY.en.download).click();await settle(()=>card.shadowRoot.querySelector('a[download]'));const link=card.shadowRoot.querySelector('a[download]');assert.equal(link.download,"family-assistant-document.pdf");assert.equal(card.shadowRoot.querySelector("iframe,embed,object,img"),null);state.members[0].revision++;await card.refresh();assert.equal(card.shadowRoot.querySelector('a[download]'),null);assert.ok(revoked.includes("blob:synthetic-document"));
});
test("document copy has equal localized key coverage",()=>{for(const lang of ["ru","uk"])assert.deepEqual(Object.keys(COPY[lang]).sort(),Object.keys(COPY.en).sort());});

test("removed document history is bounded, expands explicitly and resets on identity change",async t=>{
  const{card,state,http}=await setup(t);
  state.maintenance.documents=Array.from({length:100},(_,i)=>({id:`MD${i}`,asset_id:"MX1",revision:2,title:`Removed ${i}`,kind:"manual",note:"",status:"deleted"}));
  await card.refresh();assert.equal(card.shadowRoot.querySelectorAll("[data-document-id]").length,20);
  button(card.shadowRoot,COPY.en.more).click();assert.equal(card.shadowRoot.querySelectorAll("[data-document-id]").length,40);
  state.members[0].revision++;await card.refresh();assert.equal(card.shadowRoot.querySelectorAll("[data-document-id]").length,20);assert.equal(http.length,0);
});

test("media identifiers ending in newline are rejected before transport",async()=>{
  const {downloadDocument}=await import("../custom_components/family_assistant/frontend/media-client.js");
  let calls=0;const hass={fetchWithAuth:async()=>{calls++;}};
  for(const options of [{entryId:"entry\n",id:"M1"},{entryId:"entry",id:"M1\n"}]){
    await assert.rejects(downloadDocument(hass,{...options,revision:1,isCurrent:()=>true}),e=>e.code==="media_invalid");
  }
  assert.equal(calls,0);
});
