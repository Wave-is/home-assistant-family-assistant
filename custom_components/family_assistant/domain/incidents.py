"""An announced family incident is always closed; unsent stale alerts are cancelled."""

from .context import Context


def open_incident(ctx: Context, incident_id, key, data, *, recipient="family"):
    current = ctx.state["incidents"].get(incident_id)
    if current and current["state"] == "open":
        return current
    generation = current["generation"] + 1 if current else 1
    notification_ctx = Context(
        ctx.state, ctx.actor, ctx.now, f"incident:{incident_id}:{generation}"
    )
    event_id = notification_ctx.notify(recipient, key, data)
    record = {
        "id": incident_id,
        "generation": generation,
        "state": "open",
        "opened_at": ctx.now.isoformat(),
        "event_id": event_id,
        "recipient": recipient,
    }
    ctx.state["incidents"][incident_id] = record
    return record


def close_incident(ctx: Context, incident_id, key, data):
    record = ctx.state["incidents"].get(incident_id)
    if not record or record["state"] != "open":
        return
    event = ctx.state["outbox"][record["event_id"]]
    # 'sending' is uncertain: completion may race an already accepted message.
    announced = any(
        d["state"] in {"sent", "sending", "uncertain"} for d in event.get("deliveries", {}).values()
    )
    if event["state"] not in {"sent", "resolved"}:
        event["state"] = "superseded"
    record.update(state="closed", closed_at=ctx.now.isoformat())
    if announced:
        notification_ctx = Context(
            ctx.state, ctx.actor, ctx.now, f"incident:{incident_id}:{record['generation']}:close"
        )
        record["closure_event_id"] = notification_ctx.notify(
            record.get("recipient", "family"), key, data
        )
