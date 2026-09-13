/* Explicit card reads; no HA state access, source IDs, links or browser persistence. */
import {HOME_STATUS_COPY} from "./home-status-copy.js";

const el=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
const copy=card=>HOME_STATUS_COPY[card._config?.language||card._hass?.language?.split("-")[0]]||HOME_STATUS_COPY.en;
const marker=card=>JSON.stringify([card._generation,card._entry,card._hass?.user?.id,card._data?.actor,card._data?.role,card._data?.members?.find(row=>row.id===card._data.actor)?.revision,card._data?.settings?.modules?.includes("home_status"),card._data?.read_only,card._data?.home_status_access]);
const allowed=card=>card._view==="home_status"&&card._data&&!card._data.read_only&&card._data.role!=="guest"&&card._data.settings?.modules?.includes("home_status")&&typeof card._data.home_status_access==="string";

export function clearHomeStatus(card){card._homeStatus=null;card._homeStatusMarker=null;card._homeStatusError=null;}

export async function refreshHomeStatus(card,current){
  if(!allowed(card)){clearHomeStatus(card);return;}
  if(card._homeStatusMarker!==marker(card))clearHomeStatus(card);
  if(!card._homeStatusRequested)return;
  card._homeStatusRequested=false;
  clearHomeStatus(card);
  const captured=marker(card);
  try{
    const result=await card._hass.callWS({type:"family_assistant/home_status",entry_id:card._entry});
    if(!current()||captured!==marker(card)||!allowed(card))return;
    if(!result||result.access_marker!==card._data.home_status_access||!Array.isArray(result.energy)||!Array.isArray(result.active)||!Array.isArray(result.groups)||typeof result.generated_at!=="string")throw new Error("invalid_response");
    card._homeStatus=result;card._homeStatusMarker=captured;
  }catch{
    if(current()&&captured===marker(card)){clearHomeStatus(card);card._homeStatusError=true;}
  }
}

export function renderHomeStatus(card,body){
  const t=copy(card),wrap=el("section",undefined,"home-status");
  wrap.append(el("p",t.note,"sub"),el("p",t.configure,"sub"),el("p",t.manual,"sub"));
  const refresh=el("button",t.refresh);refresh.type="button";refresh.dataset.homeStatusRefresh="true";
  refresh.addEventListener("click",()=>{if(card._view==="home_status"&&!card._loading){card._homeStatusRequested=true;void card.refresh();}});wrap.append(refresh);
  body.append(wrap);
  if(!allowed(card)){clearHomeStatus(card);wrap.append(el("p",t.unavailable,"empty"));return;}
  if(card._homeStatusError){wrap.append(el("p",t.unavailable,"notice"));return;}
  const data=card._homeStatus;
  if(!data||card._homeStatusMarker!==marker(card)){wrap.append(el("p",card._loading?t.loading:t.refresh,"empty"));return;}
  wrap.append(el("p",`${t.generated}: ${data.generated_at}`,"sub"));
  const sections=[[t.energy,data.energy],[t.active,data.active],...data.groups.slice(0,8).map(group=>[`${group.title} (${group.id})`,group.rows])];
  let count=0;
  for(const [title,rows]of sections){
    if(!Array.isArray(rows)||!rows.length)continue;
    const section=el("section",undefined,"home-status-section");section.append(el("h3",title));wrap.append(section);
    for(const row of rows.slice(0,64)){
      count++;const line=el("div",undefined,"item");line.dataset.quality=row.quality;line.append(el("strong",String(row.label||"").slice(0,80)));
      let value;
      if(row.quality!=="ok")value=t[row.quality==="unavailable"?"unavailable_state":row.quality]||t.invalid_state;
      else if(typeof row.value==="number"&&Number.isFinite(row.value))value=`${row.value} ${row.unit}`;
      else if(typeof row.reported_state==="string")value=`${t.reported}: ${t["state_"+row.reported_state]||t.invalid_state}`;
      else value=t.invalid_value;
      line.append(el("p",value));
      if(row.quality==="ok"&&typeof row.active==="boolean")line.append(el("p",t[row.active?"matched":"not_matched"],"sub"));
      if(typeof row.report_age_seconds==="number"&&Number.isFinite(row.report_age_seconds))line.append(el("p",`${t.age}: ${Math.floor(row.report_age_seconds)} · ${row.freshness_basis||""}`,"sub"));
      section.append(line);
    }
  }
  if(!count)wrap.append(el("p",t.empty,"empty"));
}
