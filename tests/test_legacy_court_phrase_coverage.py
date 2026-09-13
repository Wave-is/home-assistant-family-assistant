"""Generic examples cover every original positive/negative pattern family.

This is recognition acceptance, not a claim that all household prose or custom
rules were imported. Names and consequences are deliberately fictional.
"""

import pytest

from custom_components.family_assistant.court.parser import parse_message
from custom_components.family_assistant.court.responses import MINUS_VARIANTS, PLUS_VARIANTS

MEMBERS = [{"id": "child", "name": "Example", "aliases": [], "role": "child", "active": True}]

POSITIVE = [
    "+1",
    "плюсик",
    "плюс",
    "добавь один балл",
    "заслужил плюс",
    "похвалить",
    "молодец",
    "молодцы",
    "умница",
    "хорошо себя вел",
    "помог",
    "сама все сделала",
    "сам все убрал",
    "сделал уроки",
    "выполнил просьбу",
    "выполнена просьба",
    "заслужил похвалу",
    "вел себя хорошо",
    "порадовал",
]
NEGATIVE = [
    "-1",
    "минус",
    "косяк",
    "накосячил",
    "снять один балл",
    "получает минус",
    "наказать",
    "плохо себя вел",
    "не слушался",
    "не сделал",
    "не убрал",
    "не выполнил",
    "опять не готов",
    "отказался",
    "нагрубил",
    "соврал",
    "обманул",
    "забыл",
    "разбил",
    "разбито",
    "сломал",
    "сломано",
    "устроил скандал",
]


@pytest.mark.parametrize(
    "kind,phrase", [("plus", p) for p in POSITIVE] + [("minus", p) for p in NEGATIVE]
)
def test_all_original_assessment_pattern_families_are_recognized(kind, phrase):
    parsed = parse_message(f"Example {phrase} за конкретный поступок", members=MEMBERS)
    assert parsed.action == "assessments"
    assert [(a.child, a.kind) for a in parsed.assessments] == [("child", kind)]


@pytest.mark.parametrize(
    "phrase", ["не молодец", "не помог", "не нагрубил", "не соврал", "без плюса"]
)
def test_negation_does_not_become_an_assessment(phrase):
    parsed = parse_message(f"Example {phrase}", members=MEMBERS)
    assert parsed.action != "assessments"


@pytest.mark.parametrize(
    "phrase",
    ["какие минусы у детей?", "за что минусы?", "проверь в журнале минусы", "история косяков"],
)
def test_original_history_questions_are_reads_not_new_scores(phrase):
    assert parse_message(phrase, members=MEMBERS).action == "history"


def test_russian_humor_banks_are_retained_without_hardcoded_consequence():
    assert len(PLUS_VARIANTS) == len(MINUS_VARIANTS) == 20
    assert len(set(PLUS_VARIANTS)) == len(set(MINUS_VARIANTS)) == 20
    assert all("бабушк" not in text.casefold() for text in (*PLUS_VARIANTS, *MINUS_VARIANTS))
