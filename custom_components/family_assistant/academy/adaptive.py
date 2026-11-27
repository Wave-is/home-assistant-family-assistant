"""Pure, event-sourced learning state for one trusted household/member binding.

Caller must authorize the binding, supply local dates, serialize writes and
persist the journal atomically. This module does not expose an HA endpoint.
"""

import hashlib
import json
from copy import deepcopy
from datetime import date, timedelta

from .fraction_extensions import PREREQUISITES, SKILLS, extended_task, fingerprint, grade

INTERVALS = (1, 3, 7, 14, 30)
SCHEMA = 1
MAX_EVENTS = 20000


def _day(value):
    if type(value) is not str:
        raise ValueError("invalid day")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value or parsed > date(9999, 11, 30):
        raise ValueError("invalid day")
    return parsed


def _token(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.isprintable():
        raise ValueError("invalid identifier")
    return value


def _seed(key):
    return int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")


def _empty_skill():
    return {"status": "unknown", "attempts": 0, "correct": 0, "assisted": 0,
            "level": 1, "streak": 0, "forms": [], "transfer": False,
            "provisional_on": None, "due": None, "interval": 0,
            "last_review": None, "seen": []}


class LearningEngine:
    """Deterministic state; JSON journal is private and never a learner projection."""

    def __init__(self, household: str, member: str, revision: int):
        if type(revision) is not int or revision < 1:
            raise ValueError("invalid revision")
        self.binding = (_token(household), _token(member), revision)
        self.skills = {skill: _empty_skill() for skill in SKILLS}
        self.sessions = {}
        self.active = None
        self.events = []
        self.receipts = {}
        self.last_day = None

    def dumps(self):
        return json.dumps({"schema": SCHEMA, "binding": self.binding,
                           "events": self.events}, ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def loads(cls, data, *, household, member, revision):
        obj = json.loads(data)
        engine = cls(household, member, revision)
        if obj["schema"] != SCHEMA or obj["binding"] != list(engine.binding):
            raise ValueError("schema or identity mismatch")
        if not isinstance(obj["events"], list) or len(obj["events"]) > MAX_EVENTS:
            raise ValueError("invalid journal size")
        for event in obj["events"]:
            before = len(engine.events)
            engine.apply(**event)
            if len(engine.events) != before + 1:
                raise ValueError("noncanonical journal event")
        return engine

    def knowledge(self, day):
        """Parent/internal projection; caller must enforce current family roles."""
        today = _day(day)
        result = {}
        for skill, state in self.skills.items():
            status = state["status"]
            if state["due"] and today >= _day(state["due"]) and status in ("provisional", "retained"):
                status = "review_due"
            result[skill] = {k: state[k] for k in ("attempts", "correct", "assisted", "level", "due")}
            result[skill]["status"] = status
            result[skill]["accuracy"] = (state["correct"] / state["attempts"]
                                         if state["attempts"] else None)
        return result

    def _unlocked(self, skill):
        return all(self.skills[s]["status"] in ("provisional", "retained")
                   for s in PREREQUISITES[skill])

    def _plan(self, session_id, day):
        used = set()
        slots = []

        def add(skill, template, mode):
            state = self.skills[skill]
            base = _seed(f"{session_id}:{len(slots)}:{template}")
            levels = (state["level"], *(n for n in (1, 2, 3) if n != state["level"]))
            for level in levels:
                for offset in range(256):
                    task = extended_task(template, (base + offset) % 2**32, level)
                    key = fingerprint(skill, task)
                    if key not in used and key not in state["seen"]:
                        used.add(key)
                        slots.append({"skill": skill, "task": task, "mode": mode,
                                      "hints": 0, "result": None})
                        return

        due = sorted((s for s in SKILLS if self._unlocked(s) and self.skills[s]["due"]
                      and self.skills[s]["due"] <= day), key=lambda s: self.skills[s]["due"])
        for skill in due[:2]:
            add(skill, SKILLS[skill][-1], "review")
        focus = next((s for s in SKILLS if self._unlocked(s)
                      and self.skills[s]["status"] not in ("provisional", "retained")), None)
        if focus:
            forms = SKILLS[focus]
            add(focus, forms[0], "practice")
            add(focus, forms[1], "practice")
            add(focus, forms[-1], "exit")
        return slots

    def current(self):
        if self.active is None:
            return None
        session = self.sessions[self.active]
        slot = session["slots"][session["position"]]
        return {"session_id": self.active, "status": session["status"],
                "position": session["position"], "total": len(session["slots"]),
                "mode": slot["mode"], "skill": slot["skill"],
                "hints_used": slot["hints"],
                "task": slot["task"].public(assessment=slot["mode"] != "practice")}

    def report(self, session_id):
        session = self.sessions[session_id]
        if session["status"] != "completed":
            raise ValueError("session not completed")
        rows = [dict(slot["result"], skill=slot["skill"], mode=slot["mode"],
                     task_id=slot["task"].task_id) for slot in session["slots"]]
        return {"session_id": session_id, "results": rows,
                "independent_correct": sum(r["independent"] and r["correct"] for r in rows),
                "independent_total": sum(r["independent"] for r in rows)}

    def apply(self, request_id, action, day, **payload):
        """Idempotent commands. Invalid answer does not advance or enter the journal."""
        _token(request_id)
        _day(day)
        event = dict(request_id=request_id, action=action, day=day, **payload)
        if request_id in self.receipts:
            old, response = self.receipts[request_id]
            if old != event:
                raise ValueError("request conflict")
            return deepcopy(response)
        if self.last_day and day < self.last_day:
            raise ValueError("date moved backwards")
        if len(self.events) >= MAX_EVENTS:
            raise ValueError("journal capacity reached")
        response = self._execute(action, day, request_id, payload)
        if response.get("status") != "invalid":
            self.last_day = day
            self.events.append(deepcopy(event))
            self.receipts[request_id] = (deepcopy(event), deepcopy(response))
        return deepcopy(response)

    def _execute(self, action, day, request_id, payload):
        if action == "start":
            if payload or self.active is not None:
                raise ValueError("session already active or invalid start")
            slots = self._plan(request_id, day)
            if not slots:
                pending = any(self._unlocked(s) and (self.skills[s]["status"] not in
                              ("provisional", "retained") or (self.skills[s]["due"]
                              and self.skills[s]["due"] <= day)) for s in SKILLS)
                return {"status": "no_work", "reason": "fresh_items_unavailable" if pending
                        else "nothing_due"}
            self.active = request_id
            self.sessions[request_id] = {"status": "active", "position": 0, "slots": slots}
            return self.current()
        if self.active is None or payload.get("session_id") != self.active:
            raise ValueError("stale session")
        session = self.sessions[self.active]
        if action in ("pause", "resume"):
            expected = "active" if action == "pause" else "paused"
            if set(payload) != {"session_id"} or session["status"] != expected:
                raise ValueError("invalid transition")
            session["status"] = "paused" if action == "pause" else "active"
            return self.current()
        if session["status"] != "active":
            raise ValueError("session paused")
        slot = session["slots"][session["position"]]
        task = slot["task"]
        keys = {"session_id", "task_id"} | ({"answer"} if action == "answer" else set())
        if set(payload) != keys or payload.get("task_id") != task.task_id:
            raise ValueError("stale task or invalid payload")
        if action in ("hint", "reveal") and slot["mode"] != "practice":
            raise ValueError("assessment is independent")
        if action == "hint":
            if slot["hints"] >= len(task.hints):
                raise ValueError("no more hints")
            slot["hints"] += 1
            return {"status": "hint", "text": task.hints[slot["hints"] - 1]}
        if action not in ("answer", "reveal"):
            raise ValueError("unknown action")
        if action == "answer":
            result = grade(task, payload["answer"])
            if result.status == "invalid":
                return {"status": "invalid", "code": result.code}
            correct = result.status == "correct"
        else:
            correct = False
        independent = action == "answer" and slot["hints"] == 0
        slot["result"] = {"correct": correct, "independent": independent,
                          "hints": slot["hints"], "revealed": action == "reveal",
                          "solution": task.solution}
        self._evidence(slot, day)
        session["position"] += 1
        response = {"status": "recorded"}
        if slot["mode"] == "practice":
            response.update(slot["result"])
        if session["position"] == len(session["slots"]):
            session["status"] = "completed"
            self.active = None
            response.update(status="completed", report=self.report(payload["session_id"]))
        else:
            response["next"] = self.current()
        return response

    def _evidence(self, slot, day):
        state = self.skills[slot["skill"]]
        result, task = slot["result"], slot["task"]
        if state["status"] == "unknown":
            state["status"] = "learning"
        key = fingerprint(slot["skill"], task)
        if key in state["seen"]:
            return
        state["seen"].append(key)
        if not result["independent"]:
            state["assisted"] += 1
            return
        state["attempts"] += 1
        today = _day(day)
        if not result["correct"]:
            state.update(status="learning", streak=0, forms=[], transfer=False,
                         provisional_on=None, interval=0, last_review=None,
                         level=max(1, state["level"] - 1),
                         due=(today + timedelta(days=1)).isoformat())
            return
        state["correct"] += 1
        state["streak"] += 1
        if task.template not in state["forms"]:
            state["forms"].append(task.template)
        state["transfer"] |= task.template.endswith("_story")
        if state["streak"] % 2 == 0:
            state["level"] = min(3, state["level"] + 1)
        if state["status"] == "learning":
            if state["streak"] >= 3 and len(state["forms"]) >= 2 and state["transfer"]:
                state.update(status="provisional", provisional_on=day, interval=0,
                             due=(today + timedelta(days=1)).isoformat())
        elif state["due"] <= day and state["last_review"] != day:
            state["status"] = "retained"
            state["last_review"] = day
            state["interval"] = min(state["interval"] + 1, len(INTERVALS) - 1)
            state["due"] = (today + timedelta(days=INTERVALS[state["interval"]])).isoformat()


async def apply_and_save(engine, save, request_id, action, day, **payload):
    """Stage on a copy; publish only after awaited durable storage succeeds.

    Caller must hold a per-binding lock across load/apply/save/publish. The save
    callback must atomically replace its private record or raise. No I/O on replay.
    """
    household, member, revision = engine.binding
    staged = LearningEngine.loads(engine.dumps(), household=household, member=member,
                                  revision=revision)
    response = staged.apply(request_id, action, day, **payload)
    if len(staged.events) == len(engine.events):
        return engine, response
    await save(staged.dumps())
    return staged, response
