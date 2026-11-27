"""Course catalog and plan contracts."""
import json
from datetime import UTC, datetime
from fractions import Fraction
from xml.etree import ElementTree as ET

import pytest

from custom_components.family_assistant.academy.courses import (
    _grade, action, catalog, index, preview, read, save_plan,
)
from custom_components.family_assistant.academy.household import AcademyError, mutate

NOW = datetime(2026, 1, 5, tzinfo=UTC)
CONFIG = {"group":"math6","mode":"continuation","first":"g6-01","last":"g6-03",
          "start":"2026-01-05","end":"2026-01-09","days":[0,1,2,3,4],"language":"en"}


def state():
    result = {"settings":{"modules":["academy"],"timezone":"UTC"},"members":{
        id:{"id":id,"name":id,"role":role,"active":True,"revision":1}
        for id,role in [("parent","parent"),("child","child"),("sibling","child")]}}
    mutate(result,"house","parent",NOW,"enroll",
           {"member_id":"child","member_revision":1,"epoch":0,"enabled":True})
    save_plan(result,"parent",NOW,{"member_id":"child","epoch":1,"version":0,
                                  "config":CONFIG,"allow_draft":True})
    return result


def test_catalog_all_keys_and_svg():
    data = catalog()
    assert len(data["lessons"]) == 45
    assert sum(len(l["questions"]) for l in data["lessons"]) == 194
    assert len(index()["lessons"]) == 45
    for lesson in data["lessons"]:
        for q in lesson["questions"]:
            assert _grade(q["answer"],q["answer"]) == "correct"
        for d in lesson["diagrams"].values():
            root = ET.fromstring("<svg>"+d["s"]+"</svg>")
            for node in root.iter():
                assert node.tag in {"svg","text","rect","line","path","polygon","circle"}
                assert not any(k.startswith("on") or "href" in k for k in node.attrib)


def test_plan_capacity_and_dates():
    assert [r["day"] for r in preview(CONFIG)] == ["2026-01-05","2026-01-06","2026-01-07"]
    with pytest.raises(AcademyError,match="course_plan_too_short"):
        preview(CONFIG | {"end":"2026-01-05"})


def test_roundtrip_replay_and_no_early_answers():
    s = state()
    base = {"epoch":1,"version":1}
    result = action(s,"child",NOW,base | {"operation_id":"1","command":"start"})
    session = result["plan"]["session"]
    fields = base | {"session_id":session["id"],"position":0}
    req = fields | {"operation_id":"2","command":"explore_done"}
    result = action(s,"child",NOW,req)
    assert action(s,"child",NOW,req) == result
    s = json.loads(json.dumps(s))
    assert read(s,"child",NOW)["plan"]["session"]["position"] == 0
    for i,q in enumerate(catalog()["lessons"][0]["questions"]):
        req = fields | {"position":i,"operation_id":str(i+3),"command":"answer","answer":q["answer"]}
        result = action(s,"child",NOW,req)
        assert action(s,"child",NOW,req) == result
        if i == 1:
            session = result["plan"]["session"]
            assert session["independent"] and "rule" not in session
        if i == 2:
            assert result["feedback"] is None
    assert result["plan"]["independent_correct"] == 2
    assert result["plan"]["independent_total"] == 2
    assert not result["plan"]["active"]
    assert read(s,"parent",NOW,"child")["plan"]["completed"] == 1
    with pytest.raises(AcademyError):
        read(s,"sibling",NOW,"child")
