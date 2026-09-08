/* Synthetic fixture for the real FamilyCard; backend contracts have Python/HA tests. */
export function presenceNotificationState(role = "parent") {
  const members = ["owner", "parent", "adult", "child", "guest"].map((role, index) => ({
    id: role, name: `Example ${role}`, role, active: true, revision: index + 1,
  }));
  const member = members.find(item => item.id === role);
  const row = id => ({member:id,member_revision:members.find(item=>item.id===id).revision,
    binding_revision:7,source_available:true,preference_revision:null,enabled:false,
    effective:false,max_wait_minutes:720,approved_by:null});
  return {revision:1,actor:role,role,members,settings:{name:"Example household",timezone:"UTC",modules:["presence"]},
    presence:{self:{member:role,member_revision:member.revision,binding_revision:7,
      subscription_revision:null,enabled:false,can_edit:true,status:"unknown",reason:"not_shared",observed_at:null},
      shared:[],notifications:{self:row(role),...(["owner","parent"].includes(role)?{managed:[row("child")]}:{})}}};
}

export function presenceNotificationTransport(state, calls) {
  const receipts = new Map();
  return message => {
    if (message.type === "family_assistant/view") return structuredClone(state);
    if (message.type !== "family_assistant/execute") throw new Error("Unexpected fixture operation");
    calls.push(structuredClone(message));
    const p = message.payload, guardian = message.action === "presence.guardian_notification_access_set";
    if (message.action !== (guardian ? "presence.guardian_notification_access_set" : "presence.notification_access_set"))
      throw new Error("Unexpected action");
    if (receipts.has(message.operation_id)) return structuredClone(receipts.get(message.operation_id));
    const row = guardian ? state.presence.notifications.managed.find(row => row.member === p.member) : state.presence.notifications.self;
    if (!row || p.member !== row.member || p.member_revision !== row.member_revision ||
      p.binding_revision !== row.binding_revision || p.preference_revision !== row.preference_revision ||
      p.actor_member_revision !== state.members.find(item=>item.id===state.actor).revision ||
      typeof p.enabled !== "boolean" || !Number.isSafeInteger(p.max_wait_minutes) || p.max_wait_minutes < 15 || p.max_wait_minutes > 1440)
      throw Object.assign(new Error("Synthetic contract conflict"),{code:"conflict"});
    row.preference_revision = (row.preference_revision || 0) + 1;
    row.enabled = p.enabled; row.effective = p.enabled && row.source_available;
    row.max_wait_minutes = p.max_wait_minutes; row.approved_by = state.actor;
    state.revision += 1;
    const result = {member:row.member,revision:row.preference_revision,status:row.enabled?"enabled":"disabled"};
    receipts.set(message.operation_id,structuredClone(result));
    return result;
  };
}
