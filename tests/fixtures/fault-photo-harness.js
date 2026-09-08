/* Synthetic transport for the real dashboard card; HTTP decoding is tested in HA. */
export async function setupFaultCard(language = "en", role = "child") {
  const state = {
    revision: 1, actor: role, role, settings: { name: "Synthetic family", timezone: "UTC", modules: ["maintenance", "tasks"] },
    members: ["owner", "parent", "child", "adult", "guest"].map((id) => ({ id, name: id, role: id, revision: 1, active: true })),
    tasks: [],
    maintenance: { assets: [], services: [], service_logs: [], faults: [{
      id: "MF000001", revision: 1, status: "reported", summary: "Synthetic leaking filter", details: "Inspect the seal", asset_id: "MX000001",
      reporter: "child", reporter_member_revision: 1, created_at: "2026-09-08T08:00:00Z", task_id: "T000001", task_revision: 1,
      task_status: "assigned", assignee: "child", attachment_ids: [], can_upload_photo: true,
    }] },
  };
  const calls = [], http = [], receipts = new Map(), lose = new Set();
  let gate = null;
  const card = document.createElement("family-maintenance-card");
  card.setConfig({ entry_id: "synthetic", language });
  document.body.append(card);
  const api = {
    language, user: { id: `ha_${role}` },
    async callWS(message) {
      if (message.type === "family_assistant/view") return structuredClone(state);
      if (message.type !== "family_assistant/execute") throw new Error("Unexpected transport");
      calls.push(structuredClone(message));
      if (receipts.has(message.operation_id)) return structuredClone(receipts.get(message.operation_id));
      let result;
      const fault = state.maintenance.faults[0];
      if (message.action === "media.reserve") {
        if (message.payload.purpose !== "maintenance_fault" || message.payload.fault_revision !== fault.revision) throw new Error("Invalid reserve contract");
        result = { id: "M0123456789abcdef0123456789abcdef", revision: 1, status: "reserved" };
      } else {
        if (message.payload.id !== fault.id || message.payload.revision !== fault.revision || message.payload.actor_member_revision !== 1) throw new Error("Invalid fault contract");
        if (message.action === "maintenance.fault_photo_attach") {
          fault.photo_attachment = { id: message.payload.media.id, revision: 3, status: "attached", purpose: "maintenance_fault", mime_type: "image/png", size_bytes: 4 };
          fault.attachment_ids = [message.payload.media.id]; fault.can_upload_photo = false;
        } else if (message.action === "maintenance.fault_photo_purge" && role === "owner") {
          fault.photo_purge = { media_id: message.payload.media.id, reason: message.payload.reason };
          delete fault.photo_attachment; fault.attachment_ids = []; fault.can_upload_photo = true;
        } else throw new Error("Unexpected mutation");
        fault.revision++;
        result = { id: fault.id, revision: fault.revision, status: fault.status };
      }
      receipts.set(message.operation_id, result);
      if (lose.delete(message.action)) throw new Error("Synthetic lost response");
      return structuredClone(result);
    },
    async fetchWithAuth(path, init) {
      http.push({ path, method: init.method, headers: { ...init.headers }, cache: init.cache, redirect: init.redirect });
      if (gate) await gate;
      if (lose.delete(init.method)) throw new Error("Synthetic lost response");
      if (init.method === "PUT") return new Response(JSON.stringify({ id: "M0123456789abcdef0123456789abcdef", revision: 2, status: "available" }));
      // A real 1x1 PNG. UI transport is synthetic, unlike the isolated HA gate.
      const raw = atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII=");
      return new Response(Uint8Array.from(raw, (c) => c.charCodeAt(0)), { headers: { "content-type": "image/png" } });
    },
  };
  card.hass = api;
  while (!card._data || card._loading) await new Promise((resolve) => setTimeout(resolve, 0));
  return { card, state, calls, http, lose, api, deferHttp() { let done; gate = new Promise((resolve) => { done = resolve; }); return () => { gate = null; done(); }; } };
}
