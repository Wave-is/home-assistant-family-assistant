/* Fictional transport fixture; real ledger contracts are separately tested in Python/HA. */
export const MAC = "02:11:22:33:44:55";
export function admissionState(role="owner") {
  return {revision:1,actor:role,role,members:["owner","parent","adult","child","guest"].map(role=>({id:role,name:`Example ${role}`,role,active:true,revision:1})),
    settings:{name:"Example",timezone:"UTC",modules:["mikrotik"]},
    network:{writable:false,inventory:null,admission:{status:"fresh",backend:"a".repeat(64),observed_at:new Date().toISOString(),token:"b".repeat(64),
      policy_revision:null,backend_changed:false,can_edit:role==="owner",mode:"audit_only",enforcement:false,plans:[],counts:{protected:1,approved:0,unreviewed:1},
      devices:[{mac:MAC,addresses:["198.51.100.10"],candidate_name:"<img src=x onerror=alert(1)>",label:null,status:"unreviewed",warnings:["locally_administered"]},
        {mac:"02:11:22:33:44:66",addresses:["198.51.100.11"],candidate_name:"Example management",label:null,status:"protected",warnings:[]}]}}};
}
export function admissionTransport(state,calls) {
  const receipts=new Map();
  return message=>{
    if(message.type==="family_assistant/view")return structuredClone(state);
    if(message.type!=="family_assistant/execute")throw new Error("Unexpected fixture request");
    calls.push(structuredClone(message));
    if(receipts.has(message.operation_id))return structuredClone(receipts.get(message.operation_id));
    const a=state.network.admission,p=message.payload;let result;
    if(message.action==="mikrotik.admission_preview") {
      if(p.actor_revision!==1||p.observation_token!==a.token||p.policy_revision!==a.policy_revision||p.changes.length!==1)throw {code:"conflict"};
      const change=p.changes[0],device=a.devices.find(item=>item.mac===change.mac);
      const plan={id:`NA${a.plans.length+1}`,status:"preview",created_at:new Date().toISOString(),expires_at:new Date(Date.now()+120000).toISOString(),policy_revision:a.policy_revision,
        backend_changed:a.backend_changed,changes:[{mac:change.mac,before:device.label?{label:device.label}:null,after:change.approved?{label:change.label}:null}],applicable:true};
      a.plans.push(plan); result=structuredClone(plan); delete result.applicable;
    } else if(message.action==="mikrotik.admission_apply") {
      const plan=a.plans.find(item=>item.id===p.id);
      if(p.confirmed!==true||p.actor_revision!==1||plan?.applicable!==true)throw {code:"conflict"};
      for(const change of plan.changes){const device=a.devices.find(item=>item.mac===change.mac);device.label=change.after?.label??null;device.status=change.after?"approved":"unreviewed";}
      plan.status="applied";plan.applicable=false;a.policy_revision=(a.policy_revision||0)+1;a.backend_changed=false;
      result={id:plan.id,status:"applied",revision:a.policy_revision};
    } else if(message.action==="mikrotik.admission_cancel") {
      const plan=a.plans.find(item=>item.id===p.id);if(plan?.status!=="preview")throw {code:"conflict"};
      plan.status="cancelled";plan.applicable=false;result={id:plan.id,status:"cancelled"};
    } else throw new Error("Unexpected fixture action");
    state.revision++;receipts.set(message.operation_id,structuredClone(result));return result;
  };
}
