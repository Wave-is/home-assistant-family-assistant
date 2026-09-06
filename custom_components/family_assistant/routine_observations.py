"""Read only owner-approved entity states, without storing raw observations."""

from .domain.routine_validation import configuration


def collect(state, read_state):
    if "routines" not in state["settings"]["modules"]:
        return {}
    result = {}
    for entity_id in configuration(state)["entity_allowlist"]:
        observed = read_state(entity_id)
        if observed is None:
            continue
        # Unchanged states can be freshly reported; last_changed would mark them stale.
        reported = getattr(observed, "last_reported", None) or getattr(
            observed, "last_updated", None
        )
        result[entity_id] = {"state": observed.state, "observed_at": reported}
    return result
