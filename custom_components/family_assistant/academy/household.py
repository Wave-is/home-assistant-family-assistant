"""Private Academy records in the canonical Family Assistant household Store."""

from datetime import datetime
from zoneinfo import ZoneInfo

from .adaptive import LearningEngine

PARENTS = {"owner", "parent"}
ACTIONS = {"start", "answer", "hint", "reveal", "pause", "resume"}


class AcademyError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require_module(state):
    if "academy" not in state["settings"]["modules"]:
        raise AcademyError("module_disabled")


def _actor(state, actor):
    require_module(state)
    row = state["members"].get(actor)
    if not row or row.get("active") is not True or row.get("role") not in PARENTS | {"child"}:
        raise AcademyError("forbidden")
    return row


def _child(state, member):
    if not isinstance(member, str) or not 1 <= len(member) <= 80:
        raise AcademyError("invalid_field")
    row = state["members"].get(member)
    if not row or row.get("active") is not True or row.get("role") != "child":
        raise AcademyError("forbidden")
    if type(row.get("revision")) is not int or row["revision"] < 1:
        raise AcademyError("conflict")
    return row


def _record(state, member):
    return state.get("academy", {}).get(member)


def _valid(record, child):
    return bool(record and record["member_revision"] == child["revision"])


def _engine(record, household, child):
    binding = {"household": household, "member": child["id"], "revision": child["revision"]}
    journal = record["journals"].get(str(child["revision"]))
    return LearningEngine.loads(journal, **binding) if journal is not None else LearningEngine(**binding)


def _date(state, now):
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise AcademyError("invalid_field")
    return now.astimezone(ZoneInfo(state["settings"]["timezone"])).date().isoformat()


def _summary(record, child):
    current = _valid(record, child)
    return {"id": child["id"], "name": child["name"], "member_revision": child["revision"],
            "epoch": record["epoch"] if record else 0,
            "enrolled": bool(current and record["enabled"]),
            "rebind_required": bool(record and not current)}


def _target(state, actor, member):
    row = _actor(state, actor)
    if row["role"] == "child" and member not in (None, actor):
        raise AcademyError("forbidden")
    return row, _child(state, actor if member is None and row["role"] == "child" else member)


def project(state, household, actor, now, member=None):
    """No journal or receipt data in the channel projection."""
    row = _actor(state, actor)
    if row["role"] in PARENTS and member is None:
        return {"role": "parent", "students": [
            _summary(_record(state, m["id"]), m) for m in state["members"].values()
            if m.get("active") is True and m.get("role") == "child"
        ]}
    row, child = _target(state, actor, member)
    record = _record(state, child["id"])
    summary = _summary(record, child)
    parent = row["role"] in PARENTS
    result = {"role": "parent" if parent else "child", "student": summary}
    if not summary["enrolled"]:
        return result
    engine = _engine(record, household, child)
    current = engine.current()
    # A learner must not infer exit/review correctness from a live knowledge map.
    if parent or current is None:
        result["knowledge"] = engine.knowledge(_date(state, now))
    if not parent:
        result["current"] = current
        if current is None:
            completed = [s for s, data in engine.sessions.items() if data["status"] == "completed"]
            if completed:
                result["last_report"] = engine.report(completed[-1])
    return result


def _epoch(value):
    if type(value) is not int or not 0 <= value < 2**53 - 1:
        raise AcademyError("invalid_field")
    return value


def _enroll(state, actor, payload):
    if _actor(state, actor)["role"] not in PARENTS:
        raise AcademyError("forbidden")
    if set(payload) != {"member_id", "member_revision", "epoch", "enabled"}:
        raise AcademyError("invalid_field")
    child = _child(state, payload["member_id"])
    record = _record(state, child["id"])
    if _epoch(payload["member_revision"]) != child["revision"]:
        raise AcademyError("conflict")
    expected = record["epoch"] if record else 0
    if _epoch(payload["epoch"]) != expected:
        raise AcademyError("conflict")
    if type(payload["enabled"]) is not bool:
        raise AcademyError("invalid_field")
    if record and _valid(record, child) and record["enabled"] == payload["enabled"]:
        return _summary(record, child)
    if not payload["enabled"] and not _valid(record, child):
        raise AcademyError("conflict")
    record = {"member_revision": child["revision"], "epoch": _epoch(expected + 1),
              "enabled": payload["enabled"], "journals": record["journals"] if record else {}}
    state.setdefault("academy", {})[child["id"]] = record
    return _summary(record, child)


def learner_stamp(state, actor, epoch):
    row, child = _target(state, actor, actor)
    if row["role"] != "child":
        raise AcademyError("forbidden")
    record = _record(state, actor)
    if not _valid(record, child) or not record["enabled"] or record["epoch"] != _epoch(epoch):
        raise AcademyError("conflict")
    return child, record


def mutate(state, household, actor, now, action, payload):
    """Only called with a writable canonical transaction's working state."""
    if not isinstance(payload, dict):
        raise AcademyError("invalid_field")
    if action == "enroll":
        return _enroll(state, actor, payload)
    if action not in ACTIONS:
        raise AcademyError("unknown_action")
    expected = {"epoch", "operation_id"}
    if action != "start":
        expected.add("session_id")
    if action in {"answer", "hint", "reveal"}:
        expected.add("task_id")
    if action == "answer":
        expected.add("answer")
    if set(payload) != expected:
        raise AcademyError("invalid_field")
    child, record = learner_stamp(state, actor, payload["epoch"])
    operation = payload["operation_id"]
    if not isinstance(operation, str) or not 1 <= len(operation) <= 96 or not operation.isprintable():
        raise AcademyError("invalid_field")
    for key in expected & {"session_id", "task_id", "answer"}:
        if not isinstance(payload[key], str) or len(payload[key]) > (80 if key == "answer" else 128):
            raise AcademyError("invalid_field")
    engine = _engine(record, household, child)
    request = f'{record["epoch"]}:{operation}'
    prior = engine.receipts.get(request)
    # A lost response retried after midnight is still the same operation.
    day = prior[0]["day"] if prior else _date(state, now)
    args = {k: payload[k] for k in expected - {"epoch", "operation_id"}}
    before = len(engine.events)
    try:
        result = engine.apply(request, action, day, **args)
    except ValueError:
        raise AcademyError("conflict") from None
    if len(engine.events) != before:
        record["journals"][str(child["revision"])] = engine.dumps()
    return result
