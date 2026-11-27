"""Private Telegram Academy commands and scheduled intent records, no network I/O.

The manager supplies a guarded transaction, authenticated actor, trusted clock,
and bot/update IDs. Transport uses the existing durable outbox.
"""

import hashlib
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .household import AcademyError, PARENTS, _child, _engine, _record, _summary, mutate, project

KEY = "academy_message"
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
WINDOW = timedelta(minutes=30)
COMMAND = re.compile(r"^/academy(?:_[a-z]+)?(?:\s|$)", re.I)


def recognizes(content):
    return isinstance(content, str) and bool(COMMAND.match(content) or content.startswith("ac:"))


def _moment(value):
    moment = datetime.fromisoformat(value)
    if moment.utcoffset() is None:
        raise ValueError("naive time")
    return moment


def _hash(*parts):
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()[:24]


def _person(state, actor, roles):
    member = state["members"].get(actor, {})
    ident = member.get("telegram_id")
    if (member.get("active") is not True or member.get("role") not in roles
            or type(ident) is not int or ident <= 0 or ident == state.get("telegram", {}).get("group_id")
            or sum(m.get("active") is True and m.get("telegram_id") == ident
                   for m in state["members"].values()) != 1):
        raise AcademyError("forbidden")
    return member


def _enabled(state):
    return "academy" in state["settings"]["modules"]


def _stamp(state, actor):
    member = _person(state, actor, PARENTS | {"child"})
    return {"actor": actor, "revision": member["revision"], "chat_id": member["telegram_id"],
            "role": member["role"], "generation": state.get("academy_generation", 0)}


def _student(state, member):
    child = _child(state, member)
    return _summary(_record(state, member), child)


def _token(current, epoch):
    if current is None:
        return None
    return _hash(epoch, current["session_id"], current["task"]["id"], current["status"])


def _put(state, event_id, actor, now, data):
    state["outbox"].setdefault(event_id, {"id": event_id, "recipient": actor, "key": KEY,
        "data": data, "created_at": now.isoformat(), "state": "pending", "attempts": 0})


def _clock(value):
    if not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise AcademyError("invalid_field")
    return value


def _local_clock(day, value, zone):
    moment = datetime.combine(day, time.fromisoformat(value), ZoneInfo(zone))
    if moment.astimezone(UTC).astimezone(moment.tzinfo).replace(tzinfo=None) != moment.replace(tzinfo=None):
        return None
    return moment.astimezone(UTC)


def _policy_key(kind, actor, member):
    return _hash(kind, actor if kind == "report" else "", member)


def configure(state, household, actor, now, kind, args):
    """Explicit parent consent; schedule CHILD mon,tue HH:MM, reports CHILD fri HH:MM."""
    approver = _person(state, actor, PARENTS)
    if kind not in {"reminder", "report"} or len(args) not in (2, 3):
        raise AcademyError("invalid_field")
    member = args[0]
    student = _student(state, member)
    recipient = member if kind == "reminder" else actor
    key = _policy_key(kind, actor, member)
    old = state.get("academy_policies", {}).get(key, {})
    enabled = args[1] != "off"
    if not enabled:
        if len(args) != 2:
            raise AcademyError("invalid_field")
        if old:
            old.update(enabled=False, version=old["version"] + 1)
        return
    if len(args) != 3 or not student["enrolled"]:
        raise AcademyError("invalid_field")
    days = args[1].lower().split(",")
    if not days or any(d not in DAYS for d in days) or (kind == "report" and len(days) != 1):
        raise AcademyError("invalid_field")
    clock = _clock(args[2])
    target = _person(state, recipient, {"child"} if kind == "reminder" else PARENTS)
    record = {"kind": kind, "household": household, "actor": actor,
              "actor_revision": approver["revision"], "recipient": recipient,
              "recipient_revision": target["revision"], "chat_id": target["telegram_id"],
              "member": member, "member_revision": student["member_revision"],
              "epoch": student["epoch"], "enabled": True, "days": sorted(set(days), key=DAYS.index),
              "clock": clock, "exceptions": [], "version": old.get("version", 0) + 1,
              "created_at": now.isoformat(), "last_period": old.get("last_period", "")}
    state.setdefault("academy_policies", {})[key] = record


def skip(state, actor, args):
    _person(state, actor, PARENTS)
    if len(args) != 2:
        raise AcademyError("invalid_field")
    member, raw = args
    _child(state, member)
    day = date.fromisoformat(raw)
    if day.isoformat() != raw:
        raise AcademyError("invalid_field")
    policy = state.get("academy_policies", {}).get(_policy_key("reminder", actor, member))
    if not policy or not policy["enabled"]:
        raise AcademyError("conflict")
    exceptions = sorted(set(policy["exceptions"]) | {raw})
    if len(exceptions) > 60:
        raise AcademyError("invalid_field")
    policy.update(exceptions=exceptions, version=policy["version"] + 1)


def disable(state):
    """Called inside the existing settings transaction; progress is retained."""
    state["academy_generation"] = state.get("academy_generation", 0) + 1
    for policy in state.get("academy_policies", {}).values():
        if policy["enabled"]:
            policy.update(enabled=False, version=policy["version"] + 1)


def _policy_current(state, policy):
    try:
        approver = _person(state, policy["actor"], PARENTS)
        target = _person(state, policy["recipient"], {"child"} if policy["kind"] == "reminder" else PARENTS)
        student = _student(state, policy["member"])
        return (_enabled(state) and policy["enabled"] is True
                and approver["revision"] == policy["actor_revision"]
                and target["revision"] == policy["recipient_revision"]
                and target["telegram_id"] == policy["chat_id"]
                and student["enrolled"] and student["member_revision"] == policy["member_revision"]
                and student["epoch"] == policy["epoch"]
                and policy["recipient"] == (policy["member"] if policy["kind"] == "reminder" else policy["actor"]))
    except (AcademyError, KeyError, TypeError, ValueError):
        return False


def tick(state, now):
    """At most one reminder per local day and report per ISO week, no backlog."""
    if not _enabled(state) or not state.get("academy_policies"):
        return
    zone = state["settings"]["timezone"]
    day = now.astimezone(ZoneInfo(zone)).date()
    for key, policy in state["academy_policies"].items():
        if not _policy_current(state, policy) or DAYS[day.weekday()] not in policy["days"]:
            continue
        if day.isoformat() in policy["exceptions"]:
            continue
        year, week, _ = day.isocalendar()
        period = day.isoformat() if policy["kind"] == "reminder" else f"{year:04}-W{week:02}"
        if period <= policy["last_period"]:
            continue
        due = _local_clock(day, policy["clock"], zone)
        if due is None or not due <= now < due + WINDOW or due < _moment(policy["created_at"]):
            continue
        actor = policy["recipient"]
        data = {**_stamp(state, actor), "kind": policy["kind"], "policy": key,
                "version": policy["version"], "period": period, "day": day.isoformat(),
                "timezone": zone, "expires_at": (due + WINDOW).isoformat()}
        _put(state, "academy:scheduled:" + _hash(key, period), actor, now, data)
        policy["last_period"] = period


def _learner_view(state, household, actor, now):
    return project(state, household, actor, now)


def handle(state, household, actor, now, bot_id, update_id, content, *, private, quoted=None):
    """Consume explicit Academy commands/callbacks or replies to Academy messages.

    The update's mutation and reply intent commit together. Group use is silently
    consumed. Quoted text is never authority; only the recorded question token is.
    """
    if not recognizes(content) and quoted is None:
        return False
    if not private or not _enabled(state):
        return True
    event_id = f"academy:tg:{bot_id}:{update_id}"
    if event_id in state["outbox"]:
        return True
    try:
        stamp = _stamp(state, actor)
    except AcademyError:
        return True
    if quoted is not None and not recognizes(content):
        token = quoted.get("question_token")
        content = f"/academy_answer {token} {content}" if token else "/academy"
    command, _, rest = content.partition(" ")
    if content.startswith("ac:"):
        parts = content.split(":")
        command = "/academy_" + parts[1] if len(parts) == 3 else "/academy_invalid"
        rest = parts[2] if len(parts) == 3 else ""
    command = command.lower()
    feedback = ""
    student = None
    try:
        if stamp["role"] in PARENTS:
            if command == "/academy":
                pass
            elif command in ("/academy_schedule", "/academy_reports"):
                configure(state, household, actor, now,
                          "reminder" if command == "/academy_schedule" else "report", rest.split())
                feedback = "Schedule saved."
            elif command == "/academy_skip":
                skip(state, actor, rest.split())
                feedback = "Date skipped."
            else:
                raise AcademyError("forbidden")
        else:
            view = _learner_view(state, household, actor, now)
            student = view["student"]
            current = view.get("current")
            if command != "/academy":
                if not student["enrolled"]:
                    raise AcademyError("forbidden")
                action = command.removeprefix("/academy_")
                token, _, answer = rest.partition(" ")
                payload = {"epoch": student["epoch"], "operation_id": f"tg:{bot_id}:{update_id}"}
                if action == "start":
                    if rest or current is not None:
                        raise AcademyError("conflict")
                else:
                    if current is None or token != _token(current, student["epoch"]):
                        raise AcademyError("conflict")
                    payload["session_id"] = current["session_id"]
                    if action in {"answer", "hint", "reveal"}:
                        payload["task_id"] = current["task"]["id"]
                    if action == "answer":
                        payload["answer"] = answer
                    elif answer:
                        raise AcademyError("invalid_field")
                result = mutate(state, household, actor, now, action, payload)
                if result.get("status") == "hint":
                    feedback = result["text"]
                elif result.get("status") == "invalid":
                    feedback = "Enter a valid number or fraction."
                elif result.get("status") == "no_work":
                    feedback = "No new exercises due right now."
                elif result.get("solution"):
                    feedback = ("Well done! " if result["correct"] else "Review: ") + result["solution"]
                elif result.get("status") == "recorded":
                    feedback = "Answer recorded. Feedback follows at the end."
    except (AcademyError, ValueError):
        feedback = "Unable to complete this action. Open /academy for current options."
    data = {**stamp, "kind": "reply", "household": household, "bot_id": bot_id,
            "feedback": feedback, "expires_at": (now + timedelta(minutes=5)).isoformat()}
    if stamp["role"] == "child":
        view = _learner_view(state, household, actor, now)
        student = view["student"]
        data["student"] = student["member_revision"], student["epoch"], student["enrolled"]
        data["student"] = list(data["student"])
        data["question_token"] = _token(view.get("current"), student["epoch"])
    _put(state, event_id, actor, now, data)
    return True


def current(state, event, now):
    """Recheck identities, consent, enrollment, expiry and current question."""
    try:
        data = event["data"]
        now = _moment(now) if isinstance(now, str) else now
        if (event["key"] != KEY or not _enabled(state) or event["recipient"] != data["actor"]
                or _stamp(state, data["actor"]) != {k: data[k] for k in
                    ("actor", "revision", "chat_id", "role", "generation")}
                or not _moment(event["created_at"]) <= now < _moment(data["expires_at"])):
            return False
        if data["kind"] == "reply":
            if data["role"] == "child":
                view = _learner_view(state, data["household"], data["actor"], now)
                student = view["student"]
                return (data["student"] == [student["member_revision"], student["epoch"], student["enrolled"]]
                        and data["question_token"] == _token(view.get("current"), student["epoch"]))
            return data["role"] in PARENTS
        policy = state["academy_policies"][data["policy"]]
        return (_policy_current(state, policy) and policy["recipient"] == data["actor"]
                and policy["kind"] == data["kind"] and policy["version"] == data["version"]
                and policy["last_period"] == data["period"]
                and state["settings"]["timezone"] == data["timezone"])
    except (AcademyError, KeyError, TypeError, ValueError, AttributeError):
        return False


def target(state, event, now):
    if not current(state, event, now):
        return None
    data = event["data"]
    return {"channel": "telegram", "id": data["chat_id"],
            "language": state["members"][data["actor"]].get("language", "en")}


def _weekly(state, policy, day):
    child = _child(state, policy["member"])
    engine = _engine(_record(state, child["id"]), policy["household"], child)
    start = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
    last = {e.get("session_id"): e["day"] for e in engine.events if e["action"] in {"answer", "reveal"}}
    reports = [engine.report(sid) for sid, session in engine.sessions.items()
               if session["status"] == "completed" and start <= last.get(sid, "") <= day]
    correct = sum(r["independent_correct"] for r in reports)
    total = sum(r["independent_total"] for r in reports)
    due = sum(s["status"] == "review_due" for s in engine.knowledge(day).values())
    text = f"Weekly Academy · {child['name']}\n{start} – {day}\nCompleted missions: {len(reports)}\nIndependent answers: {correct}/{total}\nSkills due for review: {due}"
    record = _record(state, child["id"])
    plan = record.get("course_plans",{}).get(str(child["revision"]))
    if plan:
        rows = [r for r in plan["results"].values() if start <= r["day"] <= day]
        text += (f"\nCourse lessons this week: {len(rows)}"
                 f"\nCourse independent answers: {sum(r['correct'] for r in rows)}/{sum(r['total'] for r in rows)}"
                 f"\nCourse plan: {len(plan['results'])}/{len(plan['schedule'])}")
    return text


def render(state, event, destination, now):
    """Return None on revocation; caller maps it to delivery_revoked."""
    selected = target(state, event, now)
    data = event["data"]
    if selected is None or destination.get("channel") != "telegram" or destination.get("id") != selected["id"]:
        return None
    if data.get("bot_id") is not None and data["bot_id"] != destination.get("bot_id"):
        return None
    buttons = []
    if data["kind"] == "reminder":
        text = "Time for your Family Academy mission! Open /academy to start or continue."
    elif data["kind"] == "report":
        text = _weekly(state, state["academy_policies"][data["policy"]], data["day"])
    elif data["role"] in PARENTS:
        children = project(state, data["household"], data["actor"], now)["students"]
        text = "Family Academy · parent settings\n" + "\n".join(
            f"{s['id']} · {s['name']} · {'enabled' if s['enrolled'] else 'not enrolled'}" for s in children)
        for policy in state.get("academy_policies", {}).values():
            if _policy_current(state, policy) and (policy["kind"] == "reminder" or policy["actor"] == data["actor"]):
                text += f"\n{policy['member']} · {policy['kind']}: {','.join(policy['days'])} {policy['clock']}"
        text += "\n/academy_schedule ID mon,tue,wed,thu,fri 17:00 (or ID off)\n/academy_skip ID YYYY-MM-DD\n/academy_reports ID fri 19:00 (or ID off)\nEnroll learners in the Home Assistant Academy card."
    else:
        view = _learner_view(state, data["household"], data["actor"], now)
        question = view.get("current")
        if not view["student"]["enrolled"]:
            text = "Ask a parent to enable your Academy learning profile."
        elif question is None:
            text = "Family Academy · /academy_start to begin your next mission."
            if report := view.get("last_report"):
                text += f"\nLast mission: {report['independent_correct']}/{report['independent_total']} independent answers."
                text += "\n" + "\n".join(r["solution"] for r in report["results"])
        else:
            token = data["question_token"]
            text = f"Family Academy · {question['position'] + 1}/{question['total']} · {question['mode']}"
            if question["status"] == "paused":
                buttons.append([{"text": "Resume", "callback_data": f"ac:resume:{token}"}])
            else:
                text += "\n" + question["task"]["prompt"]
                if question["task"]["template"] == "read_bar":
                    n, d = question["task"]["parameters"]
                    text += "\n" + "🟩" * n + "⬜" * (d - n)
                text += f"\nReply to this message or use /academy_answer {token} YOUR_ANSWER"
                if question["mode"] == "practice":
                    if question["hints_used"] < question["task"]["hint_count"]:
                        buttons.append([{"text": "Hint", "callback_data": f"ac:hint:{token}"}])
                    buttons.append([{"text": "Show solution", "callback_data": f"ac:reveal:{token}"}])
                buttons.append([{"text": "Pause", "callback_data": f"ac:pause:{token}"}])
    if data.get("feedback"):
        text = data["feedback"] + "\n\n" + text
    payload = {"chat_id": selected["id"], "text": text[:1900],
               "link_preview_options": {"is_disabled": True}}
    if data["role"] == "child":
        from .mini_auth import launch_url

        household = (data["household"] if data["kind"] == "reply" else
                     state["academy_policies"][data["policy"]]["household"])
        if url := launch_url(state, household):
            if _student(state,data["actor"])["enrolled"]:
                buttons.insert(0,[{"text":"Open Academy classroom","web_app":{"url":url}}])
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return payload
