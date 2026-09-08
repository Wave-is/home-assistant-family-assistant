/* Explicit parent-private equipment files, never inline PDF/image previews. */
import {uploadDocument,downloadDocument} from "./media-client.js";
import {DOCUMENT_COPY} from "./asset-document-copy.js";

const MIME=new Set(["application/pdf","image/jpeg","image/png","image/webp"]);
const MAX=10*1024*1024, SEGMENT=/^[A-Za-z0-9_-]{1,128}$(?![\s\S])/;
const version=x=>Number.isSafeInteger(x)&&x>0;
const same=(a,b)=>Boolean(a&&b)&&JSON.stringify(a)===JSON.stringify(b);
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text);if(cls)e.className=cls;return e;};
const copy=card=>DOCUMENT_COPY[(card._config?.language||card._hass?.language||"en").split("-")[0]]||DOCUMENT_COPY.en;
const assetById=(card,id)=>card._data?.maintenance?.assets?.find(x=>x.id===id);
const documentById=(card,id)=>card._data?.maintenance?.documents?.find(x=>x.id===id);
function frame(card){
  const d=card?._data,m=d?.members?.find(x=>x.id===d.actor);
  if(!card?.isConnected||card._error||!SEGMENT.test(card._entry||"")||!m||m.active!==true||!["owner","parent"].includes(m.role)||m.role!==d.role||!version(m.revision)||!d.settings?.modules?.includes("maintenance"))return null;
  return {entry:card._entry,generation:card._generation,user:card._hass?.user?.id??null,actor:m.id,role:m.role,actorRevision:m.revision};
}
function scope(card,asset){const f=frame(card);return f&&asset&&SEGMENT.test(asset.id||"")&&version(asset.revision)&&["active","retired"].includes(asset.status)?{...f,id:asset.id,revision:asset.revision,name:asset.name,status:asset.status}:null;}
function attachment(value){return value&&value.purpose==="equipment_document"&&value.status==="attached"&&SEGMENT.test(value.id||"")&&version(value.revision)&&MIME.has(value.mime_type)&&Number.isSafeInteger(value.size_bytes)&&value.size_bytes>0&&value.size_bytes<=MAX;}
function current(card,draft){
  if(!draft||card._assetDocumentDraft!==draft||!same(scope(card,assetById(card,draft.scope.id)),draft.scope))return false;
  if(draft.kind==="upload")return true;
  const latest=documentById(card,draft.document.id);
  if(!latest||latest.asset_id!==draft.scope.id)return false;
  return same(latest,draft.document)||(draft.pending&&latest.status==="deleted"&&latest.revision===draft.document.revision+1);
}
const failure=code=>{throw Object.assign(new Error(code),{code});};
const errorCode=e=>["conflict","forbidden","media_invalid","media_too_large","media_unavailable","quota_exceeded","invalid_field","module_disabled","storage_error"].includes(e?.code)?e.code:"media_unavailable";
const request=(action,payload)=>Object.freeze({action,payload:Object.freeze(payload),operation_id:crypto.randomUUID()});
function clear(card){card._assetDocumentDraft?.controller?.abort();card._assetDocumentDraft=null;}
function revoke(item){item?.controller?.abort();if(item?.url)URL.revokeObjectURL(item.url);}
export function disposeAssetDocuments(card,{keepDraft=false}={}){if(!keepDraft)clear(card);else card._assetDocumentDraft?.controller?.abort();for(const item of card._assetDocumentDownloads?.values()||[])revoke(item);card._assetDocumentDownloads?.clear();card._assetDocumentPages?.clear();}
export function reconcileAssetDocuments(card){
  let changed=false;
  if(card._assetDocumentDraft&&!current(card,card._assetDocumentDraft)){clear(card);changed=true;}
  for(const[id,item]of card._assetDocumentDownloads||[]){if(!same(frame(card),item.frame)||!same(documentById(card,id),item.document)||!same(scope(card,assetById(card,item.document.asset_id)),item.scope)){revoke(item);card._assetDocumentDownloads.delete(id);changed=true;}}
  for(const[id,item]of card._assetDocumentPages||[]){if(!same(scope(card,assetById(card,id)),item.scope)){card._assetDocumentPages.delete(id);changed=true;}}
  return changed;
}
async function execute(card,draft,command){if(!current(card,draft))failure("conflict");return draft.hass.callWS({type:"family_assistant/execute",entry_id:draft.scope.entry,...command});}
function receipt(value,status,id,revision){if(!value||Object.keys(value).sort().join(",")!=="id,revision,status"||!SEGMENT.test(value.id||"")||value.status!==status||value.revision!==revision||(id!==null&&value.id!==id))failure("media_invalid");return Object.freeze({...value});}
async function write(card,draft,fn){
  if(card._writing||!current(card,draft))return;
  const owner={};card._assetDocumentWriteOwner=owner;card._writing=true;card._actionError=null;card.render();
  try{await fn();}catch(e){if(card._assetDocumentDraft===draft&&same(frame(card),draft.frame))card._actionError=errorCode(e);}
  finally{if(card._assetDocumentWriteOwner===owner){card._assetDocumentWriteOwner=null;card._writing=false;if(same(frame(card),draft.frame)){await card.refresh();card.render();}}}
}
async function upload(card,draft){return write(card,draft,async()=>{
  draft.attempted=true;
  if(!draft.reservation)draft.reservation=receipt(await execute(card,draft,draft.reserveRequest),"reserved",null,1);
  draft.controller=new AbortController();
  draft.available=await uploadDocument(draft.hass,{entryId:draft.scope.entry,id:draft.reservation.id,revision:draft.reservation.revision,file:draft.file,signal:draft.controller.signal,isCurrent:()=>current(card,draft)});
});}
async function commit(card,draft){return write(card,draft,async()=>{
  if(!draft.pending){
    const ref=draft.kind==="upload"?draft.available:draft.document.attachment;
    draft.pending=request(draft.kind==="upload"?"maintenance.document_attach":"maintenance.document_purge",{id:draft.scope.id,revision:draft.scope.revision,actor_member_revision:draft.scope.actorRevision,media:Object.freeze({id:ref.id,revision:ref.revision}),...(draft.kind==="upload"?{title:draft.title.trim(),kind:draft.category,note:draft.note.trim()}:{document:Object.freeze({id:draft.document.id,revision:draft.document.revision}),reason:draft.reason.trim()})});
  }
  const result=await execute(card,draft,draft.pending);
  if(!result||Object.keys(result).sort().join(",")!=="asset_id,id,revision,status"||!SEGMENT.test(result.id||"")||result.asset_id!==draft.scope.id||result.status!==(draft.kind==="upload"?"attached":"deleted")||result.revision!==(draft.kind==="upload"?1:draft.document.revision+1)||(draft.kind==="purge"&&result.id!==draft.document.id))failure("media_invalid");
  if(current(card,draft))clear(card);
});}
async function download(card,row,source){
  if(!attachment(row.attachment)||!same(scope(card,assetById(card,row.asset_id)),source)||!same(documentById(card,row.id),row))return;
  card._assetDocumentDownloads??=new Map();revoke(card._assetDocumentDownloads.get(row.id));
  const item={frame:frame(card),document:structuredClone(row),scope:source,controller:new AbortController(),loading:true};card._assetDocumentDownloads.set(row.id,item);card.render();
  const check=()=>card._assetDocumentDownloads?.get(row.id)===item&&same(frame(card),item.frame)&&same(documentById(card,row.id),item.document)&&same(scope(card,assetById(card,row.asset_id)),source);
  try{const blob=await downloadDocument(card._hass,{entryId:source.entry,id:row.attachment.id,revision:row.attachment.revision,signal:item.controller.signal,isCurrent:check});if(!check())return;item.url=URL.createObjectURL(blob);item.loading=false;}
  catch(e){if(check()){card._assetDocumentDownloads.delete(row.id);card._actionError=errorCode(e);}}
  if(same(frame(card),item.frame))card.render();
}

export function renderAssetDocuments(card,container,asset){
  reconcileAssetDocuments(card);const source=scope(card,asset);if(!source)return;const c=copy(card);
  const section=node("section",undefined,"asset-documents"),rows=(card._data.maintenance.documents||[]).filter(x=>x.asset_id===asset.id);
  section.append(node("h4",c.title),node("p",c.privacy,"sub"));
  const button=(label,callback,disabled=false)=>{const b=node("button",label);b.type="button";b.disabled=disabled||card._writing;b.addEventListener("click",()=>{if(b.isConnected&&!card._writing&&same(scope(card,assetById(card,source.id)),source))callback();});return b;};
  if(!rows.length)section.append(node("p",c.empty,"sub"));
  const archive=rows.filter(x=>x.status==="deleted").reverse(),limit=card._assetDocumentPages?.get(asset.id)?.limit||20;
  for(const row of [...rows.filter(x=>x.status!=="deleted"),...archive.slice(0,limit)]){
    const block=node("div",undefined,"item");block.dataset.documentId=row.id;block.append(node("strong",row.title),node("p",c[row.kind]||c.other,"sub"));if(row.note)block.append(node("p",row.note,"sub"));
    if(row.status==="deleted")block.append(node("p",c.deleted,"sub"));
    else if(attachment(row.attachment)){
      const actions=node("div",undefined,"actions"),downloaded=card._assetDocumentDownloads?.get(row.id);
      if(downloaded?.url){const a=node("a",c.download);a.href=downloaded.url;a.download="family-assistant-document."+({"application/pdf":"pdf","image/jpeg":"jpg","image/png":"png","image/webp":"webp"}[row.attachment.mime_type]);a.rel="noopener noreferrer";a.addEventListener("click",e=>{if(!a.isConnected||!same(frame(card),downloaded.frame)||!same(documentById(card,row.id),downloaded.document)||!same(scope(card,assetById(card,row.asset_id)),downloaded.scope)){e.preventDefault();reconcileAssetDocuments(card);}});actions.append(a);}
      else actions.append(button(downloaded?.loading?c.working:c.download,()=>download(card,row,source),downloaded?.loading));
      if(source.role==="owner")actions.append(button(c.purge,()=>{clear(card);card._assetDocumentDraft={kind:"purge",scope:source,frame:frame(card),document:structuredClone(row),reason:"",hass:card._hass};card.render();}));
      block.append(actions);
    }
    section.append(block);
  }
  if(archive.length>limit)section.append(button(c.more,()=>{card._assetDocumentPages??=new Map();card._assetDocumentPages.set(asset.id,{scope:source,limit:Math.min(5000,limit+20)});card.render();}));
  section.append(button(c.add,()=>{clear(card);card._assetDocumentDraft={kind:"upload",scope:source,frame:frame(card),file:null,title:"",category:"manual",note:"",hass:card._hass,reserveRequest:request("media.reserve",{purpose:"equipment_document",asset_id:source.id,asset_revision:source.revision,uploader_revision:source.actorRevision})};card._actionError=null;card.render();},rows.filter(x=>x.status==="attached").length>=10));
  const draft=card._assetDocumentDraft;
  if(draft&&draft.scope.id===asset.id&&current(card,draft)){
    const form=node("form");form.dataset.documentForm=draft.kind;
    form.append(node("p",c.formats,"sub"),node("p",c.warning,"sub"));
    const controls={},field=(key,label,value,max)=>{const wrap=node("label",label),i=node("input");i.name=key;i.value=value;i.maxLength=max;i.disabled=card._writing||Boolean(draft.pending);i.addEventListener("input",()=>{if(form.isConnected&&current(card,draft)&&!card._writing&&!draft.pending)draft[key]=i.value;});wrap.append(i);form.append(wrap);controls[key]=i;return i;};
    if(draft.kind==="upload"){
      const wrap=node("label",c.file),f=node("input");f.type="file";f.name="document_file";f.accept=[...MIME].join(",");f.disabled=card._writing||Boolean(draft.attempted);wrap.hidden=Boolean(draft.attempted);wrap.append(f);form.append(wrap);
      f.addEventListener("change",()=>{if(!form.isConnected||!current(card,draft)||card._writing||draft.attempted)return;draft.file=f.files?.[0]||null;card.render();});
      if(draft.file)form.append(node("p",draft.file.name||c.file,"sub"));
      field("title",c.label,draft.title,160);const label=node("label",c.kind),select=node("select");select.name="category";select.disabled=card._writing||Boolean(draft.pending);for(const value of ["manual","warranty","receipt","other"]){const o=node("option",c[value]);o.value=value;select.append(o);}select.value=draft.category;select.addEventListener("change",()=>{if(form.isConnected&&current(card,draft)&&!card._writing&&!draft.pending)draft.category=select.value;});label.append(select);form.append(label);field("note",c.note,draft.note,1000);
      if(draft.available)form.append(node("p",c.ready,"notice"));
      else form.append(button(draft.attempted?c.retry:c.upload,()=>upload(card,draft),!draft.file||!MIME.has(draft.file.type)||draft.file.size<=0||draft.file.size>MAX));
    }else{form.append(node("strong",draft.document.title),node("p",c.purge_warning,"notice"));field("reason",c.reason,draft.reason,500);}
    const notice=node("p",c.invalid,"notice");notice.role="alert";notice.hidden=true;form.append(notice);
    if(draft.kind==="purge"||draft.available){const b=button(draft.pending?c.retry:draft.kind==="upload"?c.attach:c.confirm_purge,()=>{});b.type="submit";form.append(b);}
    form.append(button(c.cancel,()=>{clear(card);card._actionError=null;card.render();}));
    form.addEventListener("submit",e=>{e.preventDefault();if(!form.isConnected||!current(card,draft)||card._writing)return;if(!draft.pending&&(draft.kind==="upload"?!draft.available||!draft.title.trim()||draft.title.length>160||draft.note.length>1000:!draft.reason.trim()||draft.reason.length>500)){notice.hidden=false;return;}commit(card,draft);});section.append(form);
  }
  container.append(section);
}
