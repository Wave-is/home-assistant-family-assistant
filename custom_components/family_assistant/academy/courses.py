"""Versioned lesson catalog and dated, persisted course plans.

This fixed question bank is draft educational content, not a reviewed mastery
assessment. Fraction mastery remains in the existing adaptive domain.
"""
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
from functools import lru_cache
import json
from pathlib import Path

from .household import AcademyError, PARENTS, _actor, _child, _date, _record, _summary, learner_stamp
from .rational import check_rational

GROUPS = {"math6", "algebra7", "geometry7", "math7", "all"}
MODES = {"continuation", "recovery"}
MAX_REQUESTS = 10000


@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name("math_6_7_v1.json").read_text(encoding="utf-8"))


def _lessons(group):
    if group not in GROUPS:
        raise AcademyError("invalid_field")
    return [lesson for lesson in catalog()["lessons"] if group == "all" or lesson["group"] == group
            or (group == "math7" and lesson["grade"] == 7)]


def index(group="all"):
    return {"version": catalog()["version"], "status": catalog()["status"],
            "lessons": [{k: lesson[k] for k in ("id", "grade", "group", "assessment", "title")}
                        for lesson in _lessons(group)]}


def _lesson(lesson_id):
    for lesson in catalog()["lessons"]:
        if lesson["id"] == lesson_id:
            return lesson
    raise AcademyError("invalid_field")


def _day(raw):
    if type(raw) is not str:
        raise AcademyError("invalid_field")
    try:
        result = date.fromisoformat(raw)
    except ValueError:
        raise AcademyError("invalid_field") from None
    if result.isoformat() != raw or not 2000 <= result.year <= 2099:
        raise AcademyError("invalid_field")
    return result


def preview(payload):
    required = {"group", "mode", "first", "last", "start", "end", "days", "language"}
    if (not required <= set(payload) <= required | {"commitment","minutes"} or payload["mode"] not in MODES
            or payload["language"] not in {"en", "uk"}):
        raise AcademyError("invalid_field")
    from .accountability import policy

    policy(payload)
    minutes = payload.get("minutes",25)
    if type(minutes) is not int or not 15 <= minutes <= 60:
        raise AcademyError("invalid_field")
    rows = _lessons(payload["group"])
    ids = [row["id"] for row in rows]
    if payload["first"] not in ids or payload["last"] not in ids:
        raise AcademyError("invalid_field")
    first, last = ids.index(payload["first"]), ids.index(payload["last"])
    start, end = _day(payload["start"]), _day(payload["end"])
    days = payload["days"]
    if (last < first or not 0 <= (end-start).days <= 366 or type(days) is not list
            or not days or any(type(d) is not int or not 0 <= d <= 6 for d in days)):
        raise AcademyError("invalid_field")
    available = [start + timedelta(days=i) for i in range((end-start).days+1)
                 if (start + timedelta(days=i)).weekday() in days]
    selected = ids[first:last+1]
    if len(available) < len(selected):
        raise AcademyError("course_plan_too_short")
    return [{"lesson": lesson, "day": day.isoformat()} for lesson, day in zip(selected, available, strict=False)]


def _grade(expected, answer):
    if type(answer) is not str or not 1 <= len(answer) <= 80:
        return "invalid"
    if expected in {"yes", "no"}:
        normalized = {"yes":"yes", "no":"no", "так":"yes", "ні":"no"}.get(answer.strip().lower())
        return "invalid" if normalized is None else "correct" if expected == normalized else "incorrect"
    return check_rational(answer, Fraction(expected.replace("−", "-").replace(",", "."))).status


def _row(state, actor, member=None, *, parent=False):
    user = _actor(state, actor)
    if parent and user["role"] not in PARENTS:
        raise AcademyError("forbidden")
    if user["role"] == "child" and member not in (None, actor):
        raise AcademyError("forbidden")
    child = _child(state, actor if user["role"] == "child" else member)
    record = _record(state, child["id"])
    summary = _summary(record, child)
    if not summary["enrolled"]:
        raise AcademyError("conflict")
    return child, record, summary


def _plan(record, child):
    return record.get("course_plans", {}).get(str(child["revision"]))


def _public(plan, today, *, parent=False):
    if plan is None:
        return None
    if plan.get("catalog_version") != catalog()["version"]:
        raise AcademyError("conflict")
    result = {k: deepcopy(plan[k]) for k in ("version", "config", "schedule", "results")}
    result["completed"] = len(plan["results"])
    result["total"] = len(plan["schedule"])
    result["independent_correct"] = sum(r["correct"] for r in plan["results"].values())
    result["independent_total"] = sum(r["total"] for r in plan["results"].values())
    result["due_unfinished"] = sum(x["day"] <= today and x["lesson"] not in plan["results"]
                                   for x in plan["schedule"])
    result["needs_review"] = [k for k,r in plan["results"].items() if r["correct"] < r["total"]]
    result["review_due"] = [k for k,r in plan["results"].items() if r.get("review_due","9999-12-31") <= today]
    result["active"] = plan["session"] is not None
    if parent or plan["session"] is None:
        return result
    s = plan["session"]
    lesson = _lesson(s["lesson"])
    lang = plan["config"]["language"]
    # Never return the raw question bank, keys, or current independent scores.
    session = {k:s[k] for k in ("lesson", "id", "position", "phase", "hinted")}
    session["title"] = lesson["title"][lang]
    session["rule"] = lesson["rule"][lang]
    session["example"] = lesson["example"][lang]
    session["fact"] = lesson["fact"][lang]
    session["diagram"] = lesson["diagrams"][lang]
    session["count"] = len(lesson["questions"])
    session["review"] = s.get("review",False)
    if s["phase"] == "questions":
        q = lesson["questions"][s["position"]]
        session["question"] = {"id": q["id"], "text": q["q"][lang],
                               "boolean": q["answer"] in {"yes","no"}}
        session["independent"] = not s.get("review",False) and _independent(plan, lesson, s["position"])
        if s["hinted"] and not session["independent"]:
            session["hint"] = q["h"][lang]
        if session["independent"]:
            # No worked answers/illustrations in the independent phase.
            for k in ("rule", "example", "fact", "diagram", "hint"):
                session.pop(k, None)
    result["session"] = session
    return result


def _independent(plan, lesson, position):
    return (lesson["assessment"] or plan["config"]["mode"] == "recovery"
            or position >= len(lesson["questions"]) // 2)


def read(state, actor, now, member=None):
    child, record, summary = _row(state, actor, member)
    result = {"student": summary, "plan": _public(_plan(record, child), _date(state, now),
                                                parent=actor != child["id"])}
    if actor != child["id"]:
        result["commitments"] = deepcopy(record.get("commitment_receipts",{}))
    return result


def save_plan(state, actor, now, payload):
    if set(payload) != {"member_id","epoch","version","config","allow_draft"}:
        raise AcademyError("invalid_field")
    child, record, student = _row(state, actor, payload["member_id"], parent=True)
    if type(payload["epoch"]) is not int or student["epoch"] != payload["epoch"]:
        raise AcademyError("conflict")
    old = _plan(record, child)
    if type(payload["version"]) is not int or payload["version"] != (old["version"] if old else 0):
        raise AcademyError("conflict")
    if payload["allow_draft"] is not True or not isinstance(payload["config"], dict):
        raise AcademyError("course_review_required")
    config = deepcopy(payload["config"])
    schedule = preview(config)
    if config.get("commitment",{}).get("enabled") and config["start"] < _date(state,now):
        raise AcademyError("invalid_field")  # no retroactive commitments
    if old and old["session"] is not None:
        raise AcademyError("course_session_active")
    plan = {"version": payload["version"]+1, "catalog_version": catalog()["version"],
            "config": config, "schedule": schedule, "results": {}, "session": None,
            "receipts": {}, "archive": (old.get("archive", []) + [
                {"version":old["version"],"config":old["config"],"results":old["results"]}
            ])[-10:] if old else []}
    record.setdefault("course_plans", {})[str(child["revision"])] = plan
    return _public(plan, _date(state, now), parent=True)


def action(state, actor, now, payload):
    if not isinstance(payload, dict) or not {"epoch","version","operation_id","command"} <= set(payload):
        raise AcademyError("invalid_field")
    child, record = learner_stamp(state, actor, payload["epoch"])
    plan = _plan(record, child)
    if (not plan or plan.get("catalog_version") != catalog()["version"]
            or type(payload["version"]) is not int or payload["version"] != plan["version"]):
        raise AcademyError("conflict")
    op = payload["operation_id"]
    if type(op) is not str or not 1 <= len(op) <= 80 or not op.isprintable():
        raise AcademyError("invalid_field")
    op = f'{record["epoch"]}:{op}'
    if op in plan["receipts"]:
        previous = plan["receipts"][op]
        if previous["payload"] != payload:
            raise AcademyError("conflict")
        return {"status":previous["result"]["status"],"feedback":previous["result"]["feedback"],
                "plan":_public(plan,_date(state,now))}
    if len(plan["receipts"]) >= MAX_REQUESTS:
        raise AcademyError("course_capacity")
    cmd, today = payload["command"], _date(state, now)
    base = {"epoch","version","operation_id","command"}
    session = plan["session"]
    feedback = None
    if cmd in {"start","review"}:
        if set(payload) != (base | {"lesson_id"} if cmd=="review" else base) or session is not None:
            raise AcademyError("conflict")
        if cmd=="review":
            lesson_id = payload["lesson_id"]
            if lesson_id not in plan["results"]:
                raise AcademyError("conflict")
        else:
            lesson_id = next((x["lesson"] for x in plan["schedule"] if x["lesson"] not in plan["results"]), None)
        if lesson_id is None:
            return {"status":"completed","plan":_public(plan,today)}
        plan["session"] = {"id":op,"lesson":lesson_id,"position":0,
                           "phase":"questions" if cmd=="start" and (plan["config"]["mode"] == "recovery" or
                           _lesson(lesson_id)["assessment"]) else "explore",
                           "review":cmd=="review","hinted":False,"rows":[]}
    else:
        expected = base | {"session_id","position"}
        if cmd == "answer":
            expected |= {"answer"}
        if (set(payload) != expected or session is None or payload["session_id"] != session["id"]
                or type(payload["position"]) is not int or payload["position"] != session["position"]):
            raise AcademyError("conflict")
        lesson = _lesson(session["lesson"])
        lang = plan["config"]["language"]
        if cmd == "explore_done" and session["phase"] == "explore":
            session["phase"] = "questions"
        elif cmd == "cancel":
            plan["session"] = None
        elif session["phase"] == "questions" and cmd in {"hint","answer"}:
            independent = not session.get("review",False) and _independent(plan,lesson,session["position"])
            question = lesson["questions"][session["position"]]
            if cmd == "hint":
                if independent:
                    raise AcademyError("forbidden")
                session["hinted"] = True
                feedback = {"hint":question["h"][lang]}
            else:
                graded = _grade(question["answer"],payload["answer"])
                if graded == "invalid":
                    return {"status":"invalid"}
                row = {"id":question["id"],"correct":graded=="correct",
                       "independent":independent and not session["hinted"]}
                session["rows"].append(row)
                session["position"] += 1
                session["hinted"] = False
                if not independent:
                    feedback = {"correct":row["correct"],"explanation":question["e"][lang]}
                if session["position"] == len(lesson["questions"]):
                    rows = session["rows"]
                    if session.get("review",False):
                        previous = plan["results"][lesson["id"]]
                        step = min(4,previous.get("review_step",0)+1) if all(r["correct"] for r in rows) else 0
                        previous.update(review_step=step,last_review=today,
                                        review_due=(_day(today)+timedelta(days=(1,3,7,14,30)[step])).isoformat())
                    else:
                        plan["results"][lesson["id"]] = {"day":today,
                            "correct":sum(r["independent"] and r["correct"] for r in rows),
                            "total":sum(r["independent"] for r in rows),
                            "missed":[r["id"] for r in rows if r["independent"] and not r["correct"]],
                            "review_due":(_day(today)+timedelta(days=1)).isoformat(),"review_step":0}
                    feedback = {"review":[{"correct":r["correct"],"explanation":q["e"][lang]}
                                         for r,q in zip(rows,lesson["questions"],strict=True)]}
                    plan["session"] = None
        else:
            raise AcademyError("conflict")
    result = {"status":"ok","feedback":feedback,"plan":_public(plan,today)}
    plan["receipts"][op] = {"payload":deepcopy(payload),
                            "result":{"status":result["status"],"feedback":deepcopy(feedback)}}
    return result
