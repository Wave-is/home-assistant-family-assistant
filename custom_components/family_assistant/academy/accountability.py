"""Explicitly reviewed learning commitments; never grade knowledge with Court points."""
from datetime import date,timedelta
from zoneinfo import ZoneInfo
from datetime import datetime

from . import courses
from .household import AcademyError


def policy(config):
    value = config.get("commitment",{"enabled":False,"points":0,"grace_days":1})
    if (type(value) is not dict or set(value) != {"enabled","points","grace_days"}
            or type(value["enabled"]) is not bool or type(value["points"]) is not int
            or not 0 <= value["points"] <= 5 or type(value["grace_days"]) is not int
            or not 1 <= value["grace_days"] <= 7
            or (value["enabled"] and value["points"] == 0)):
        raise AcademyError("invalid_field")
    return value


def review(state,actor,now,payload):
    if set(payload) != {"member_id","epoch","version","lesson","decision","confirmed_available"}:
        raise AcademyError("invalid_field")
    child,record,student = courses._row(state,actor,payload["member_id"],parent=True)
    plan = courses._plan(record,child)
    if (not plan or type(payload["epoch"]) is not int or type(payload["version"]) is not int
            or payload["epoch"] != student["epoch"] or payload["version"] != plan["version"]
            or payload["decision"] not in {"excuse","confirm_missed"}
            or type(payload["confirmed_available"]) is not bool):
        raise AcademyError("conflict")
    cfg = policy(plan["config"])
    if not cfg["enabled"]:
        raise AcademyError("forbidden")
    lesson = next((x for x in plan["schedule"] if x["lesson"] == payload["lesson"]),None)
    if lesson is None:
        raise AcademyError("invalid_field")
    # One decision per lesson per identity epoch, even if the plan is replaced.
    key = str(child["revision"])+":"+lesson["lesson"]
    receipts = record.setdefault("commitment_receipts",{})
    if key in receipts:
        if receipts[key]["decision"] != payload["decision"]:
            raise AcademyError("conflict")
        return receipts[key]
    today = date.fromisoformat(courses._date(state,now))
    if lesson["lesson"] in plan["results"] or today <= date.fromisoformat(lesson["day"])+timedelta(days=cfg["grace_days"]):
        raise AcademyError("conflict")
    receipt = {"lesson":lesson["lesson"],"day":lesson["day"],"decision":payload["decision"],
               "points":0,"court_id":None}
    if payload["decision"] == "confirm_missed":
        settings = state["settings"]
        if not payload["confirmed_available"] or "court" not in settings["modules"] or not settings.get("automatic_penalties"):
            raise AcademyError("forbidden")
        # Missing/uncertain delivery or a server outage must never be treated as
        # proof of deliberate noncompletion. A parent must confirm availability.
        notice = any(e.get("key")=="academy_message" and e.get("recipient")==child["id"]
                     and e.get("state")=="sent" and e.get("data",{}).get("kind")=="reminder"
                     and e["data"].get("day")==lesson["day"]
                     and e["data"].get("revision")==child["revision"]
                     and e["data"].get("epoch")==student["epoch"]
                     for e in state.get("outbox",{}).values())
        if not notice:
            raise AcademyError("unverified_notice")
        from ..domain import court
        from ..domain.context import Context
        zone = ZoneInfo(settings["timezone"])
        spent = sum(-r["points"] for r in state.get("court",{}).values()
                    if r.get("member")==child["id"] and r.get("status")=="active"
                    and r.get("points",0)<0 and
                    datetime.fromisoformat(r["created_at"]).astimezone(zone).date()==now.astimezone(zone).date())
        points = min(cfg["points"],max(0,settings.get("daily_penalty_cap",0)-spent))
        if points:
            result = court.handle(Context(state,state["members"][actor],now,"academy:"+key),
                "award",{"member":child["id"],"points":-points,
                         "reason":"Academy: reviewed missed learning commitment "+lesson["day"]})
            receipt.update(points=result["points"],court_id=result["id"])
    receipts[key] = receipt
    return receipt
