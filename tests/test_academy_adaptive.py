"""Synthetic fraction generation, mastery, replay and durable save checks."""

from datetime import date, timedelta
from fractions import Fraction

import pytest

from custom_components.family_assistant.academy.adaptive import LearningEngine, apply_and_save
from custom_components.family_assistant.academy.fraction_extensions import (
    SKILLS,
    extended_task,
    fingerprint,
    grade,
)

DAY = "2026-01-01"
BINDING = {"household": "synthetic-household", "member": "synthetic-child", "revision": 1}


def fresh():
    return LearningEngine(**BINDING)


def correct_answer(task):
    if task.template in ("improper_to_mixed", "mixed_story"):
        w = task.expected.numerator // task.expected.denominator
        return f"{w} {task.expected - w}"
    if task.template == "mixed_to_improper":
        return f"{task.expected.numerator}/{task.expected.denominator}"
    return str(task.expected)


@pytest.mark.parametrize("skill", SKILLS)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_extended_templates(skill, level):
    for template in SKILLS[skill]:
        for seed in [*range(128), 2**32 - 1]:
            task = extended_task(template, seed, level)
            assert task == extended_task(template, seed, level)
            assert grade(task, correct_answer(task)).status == "correct"
            assert grade(task, "1/0").status == "invalid"
            assert grade(task, "0" if task.expected else "1").status == "incorrect"
            p = task.parameters
            if skill == "fraction_value":
                assert task.expected == (p[0] * p[2] if template == "equivalent"
                                         else Fraction(p[0], p[1]))
            elif skill == "mixed_numbers":
                assert task.expected == p[0] + Fraction(p[1], p[2])
            else:
                a, b = Fraction(p[0], p[1]), Fraction(p[2], p[3])
                expected = {"addition": a+b, "subtraction": a-b,
                            "multiplication": a*b, "division": a/b}[skill]
                assert task.expected == expected >= 0
            assert not {"expected", "solution", "hints"} & task.public().keys()


def test_mixed_syntax_and_form():
    task = extended_task("improper_to_mixed", 0)
    assert grade(task, str(task.expected)).code == "mixed_number_required"
    assert grade(task, "2 4/3").status == "invalid"
    assert grade(task, "2 1/0").status == "invalid"
    task = extended_task("mixed_to_improper", 0)
    assert grade(task, "1 1/2").code == "improper_fraction_required"
    assert grade(task, "3/2").status == "correct"


def test_fingerprint_ignores_story_and_seed():
    for skill, plain, story in [("addition", "add", "add_story"),
                                ("multiplication", "multiply", "multiply_story")]:
        assert fingerprint(skill, extended_task(plain, 12)) == fingerprint(
            skill, extended_task(story, 12))


def act(engine, action, day=DAY, **kw):
    current = engine.current()
    payload = {"session_id": current["session_id"]}
    if action not in ("pause", "resume"):
        payload["task_id"] = current["task"]["id"]
    return engine.apply(f"req-{len(engine.events)}", action, day, **payload, **kw)


def answer(engine, day=DAY, wrong=False):
    session = engine.sessions[engine.active]
    task = session["slots"][session["position"]]["task"]
    return act(engine, "answer", day, answer="-99" if wrong else correct_answer(task))


def finish(engine, day=DAY):
    while engine.current():
        answer(engine, day)


def start(engine, day=DAY):
    return engine.apply(f"start-{len(engine.events)}", "start", day)


def test_unknown_and_provisional_then_retained():
    engine = fresh()
    assert engine.knowledge(DAY)["fraction_value"]["accuracy"] is None
    start(engine)
    assert len(engine.sessions[engine.active]["slots"]) == 3
    answer(engine)
    assert engine.knowledge(DAY)["fraction_value"]["status"] == "learning"
    finish(engine)
    state = engine.knowledge(DAY)["fraction_value"]
    assert state["status"] == "provisional" and state["due"] == "2026-01-02"
    assert state["level"] == 2
    assert start(engine)["skill"] == "addition"
    finish(engine)
    assert engine.knowledge(DAY)["fraction_value"]["status"] == "provisional"
    assert start(engine, "2026-01-02")["mode"] == "review"
    assert "correct" not in answer(engine, "2026-01-02")
    state = engine.knowledge("2026-01-02")["fraction_value"]
    assert state["status"] == "retained" and state["due"] == "2026-01-05"


def test_assistance_invalid_input_and_no_early_assessment_feedback():
    engine = fresh()
    start(engine)
    invalid = act(engine, "answer", answer="1/0")
    assert invalid["status"] == "invalid" and engine.current()["position"] == 0
    act(engine, "hint")
    answer(engine)
    act(engine, "reveal")
    with pytest.raises(ValueError):
        act(engine, "hint")
    with pytest.raises(ValueError):
        engine.report(engine.active)
    result = answer(engine)
    assert result["report"]["independent_total"] == 1
    assert engine.knowledge(DAY)["fraction_value"]["assisted"] == 2
    assert engine.knowledge(DAY)["fraction_value"]["status"] == "learning"


def test_resume_roundtrip_and_replay(tmp_path):
    engine = fresh()
    current = start(engine)
    act(engine, "hint")
    act(engine, "pause")
    path = tmp_path / "journal.json"
    path.write_text(engine.dumps(), encoding="utf-8")
    restored = LearningEngine.loads(path.read_text(encoding="utf-8"), **BINDING)
    assert restored.current() == engine.current()
    assert restored.apply(current["session_id"], "start", DAY) == current
    with pytest.raises(ValueError):
        restored.apply(current["session_id"], "start", "2026-01-02")
    with pytest.raises(ValueError):
        answer(restored)
    act(restored, "resume")
    assert restored.current()["hints_used"] == 1
    finish(restored)
    assert restored.knowledge(DAY)["fraction_value"]["assisted"] == 1
    with pytest.raises(ValueError):
        LearningEngine.loads(path.read_text(), **(BINDING | {"revision": 2}))


def test_wrong_review_reopens_and_reduces_level():
    engine = fresh()
    start(engine)
    finish(engine)
    start(engine, "2026-01-02")
    answer(engine, "2026-01-02", wrong=True)
    state = engine.knowledge("2026-01-02")["fraction_value"]
    assert state["status"] == "learning" and state["level"] == 1
    assert state["due"] == "2026-01-03"
    assert state["correct"] == 3 and state["attempts"] == 4


def test_review_intervals_and_workload():
    engine = fresh()
    start(engine)
    finish(engine)
    today = date.fromisoformat(DAY)
    for interval, following in [(1, 3), (3, 7), (7, 14), (14, 30), (30, 30)]:
        today += timedelta(days=interval)
        day = today.isoformat()
        assert engine.knowledge(day)["fraction_value"]["status"] == "review_due"
        for _ in range(6):
            if engine.knowledge(day)["fraction_value"]["status"] != "review_due":
                break
            start(engine, day)
            slots = engine.sessions[engine.active]["slots"]
            assert len(slots) <= 5 and sum(s["mode"] == "review" for s in slots) <= 2
            finish(engine, day)
        assert engine.knowledge(day)["fraction_value"]["due"] == (
            today + timedelta(days=following)).isoformat()


def test_stale_task_and_backdated_commands_do_not_mutate():
    engine = fresh()
    first = start(engine)
    answer(engine)
    before = engine.dumps()
    with pytest.raises(ValueError):
        engine.apply("stale", "answer", DAY, session_id=first["session_id"],
                     task_id=first["task"]["id"], answer="1")
    with pytest.raises(ValueError):
        act(engine, "pause", "2025-12-31")
    assert engine.dumps() == before


@pytest.mark.asyncio
async def test_atomic_save_failure_and_replay():
    engine = fresh()
    saved = []

    async def fail(_):
        raise OSError("synthetic disk failure")

    async def save(data):
        saved.append(data)

    with pytest.raises(OSError):
        await apply_and_save(engine, fail, "start", "start", DAY)
    assert engine.current() is None and not engine.events
    staged, result = await apply_and_save(engine, save, "start", "start", DAY)
    assert engine.current() is None and staged.current() == result
    assert LearningEngine.loads(saved[0], **BINDING).current() == result
    replay, same = await apply_and_save(staged, save, "start", "start", DAY)
    assert replay is staged and same == result and len(saved) == 1
