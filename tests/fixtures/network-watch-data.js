import {admissionState} from "./network-admission-data.js";
export function watchState(role="parent") {
  const state=admissionState(role);
  state.network.admission.watch={actor_revision:1,watch_revision:null,enabled:false,effective:false,
    min_interval_minutes:30,baseline_at:null,seen_count:0,pending_count:0,capacity_blocked:false,private_chat_ready:true};
  return state;
}
export function watchTransport(state,calls){
  const receipts=new Map();
  return message=>{
    if(message.type==="family_assistant/view")return structuredClone(state);
    if(message.type!=="family_assistant/execute"||message.action!=="mikrotik.admission_watch_set")throw new Error("Unexpected fixture request");
    calls.push(structuredClone(message));
    if(receipts.has(message.operation_id))return structuredClone(receipts.get(message.operation_id));
    const p=message.payload,w=state.network.admission.watch;
    if(p.actor_revision!==w.actor_revision||p.watch_revision!==w.watch_revision||typeof p.enabled!=="boolean"||!Number.isSafeInteger(p.min_interval_minutes)||p.min_interval_minutes<5||p.min_interval_minutes>1440)throw {code:"conflict"};
    if(p.enabled?p.observation_token!==state.network.admission.token:"observation_token" in p)throw {code:"network_conflict"};
    Object.assign(w,{watch_revision:(w.watch_revision||0)+1,enabled:p.enabled,effective:p.enabled,min_interval_minutes:p.min_interval_minutes,
      baseline_at:p.enabled?new Date().toISOString():null,seen_count:p.enabled?state.network.admission.devices.length:0,pending_count:0,capacity_blocked:false});
    const result={watch_revision:w.watch_revision,enabled:w.enabled};state.revision++;receipts.set(message.operation_id,result);return structuredClone(result);
  };
}
