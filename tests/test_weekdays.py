"""Weekday arithmetic and original-request grounding are deterministic."""

from copy import deepcopy

import pytest

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.domain.weekdays import (
    DAYS,
    GROUPS,
    day_expressions,
    grounded_days,
    parse_days,
)
from tools.evaluate_model import NOW, fixture


@pytest.mark.parametrize(
    "days,alias", [(list(days), alias) for days, aliases in GROUPS for alias in aliases]
)
def test_group_aliases(days, alias):
    assert parse_days(alias) == days
    assert parse_days(" " + alias.upper() + ". ") == days


@pytest.mark.parametrize(
    "day,alias", [(day, alias) for day, aliases in enumerate(DAYS) for alias in aliases]
)
def test_named_day_aliases(day, alias):
    assert parse_days(alias) == [day]


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("on Monday and Wednesday", [0, 2]),
        ("в понедельник и среду", [0, 2]),
        ("у п’ятницю та неділю", [4, 6]),
        ("tue, fri", [1, 4]),
        ("сб; пн; сб", [0, 5]),
        ("каждое воскресенье", [6]),
    ],
)
def test_named_lists(expression, expected):
    assert parse_days(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        None,
        True,
        [],
        {},
        "",
        " ",
        "x" * 161,
        "0,1",
        "not weekdays",
        "не по будням",
        "weekdays and weekends",
        "Monday except Friday",
        "Monday,",
        "next week",
        "через неделю",
    ],
)
def test_unknown_ambiguous_negative_or_numeric_expressions_are_not_guessed(expression):
    with pytest.raises(DomainError, match="invalid_alarm_days"):
        parse_days(expression)


def test_materialization_grounds_days_in_current_request_and_keeps_original_immutable():
    value = {
        "kind": "commands",
        "commands": [
            {
                "action": "alarms.save",
                "payload": {
                    "member": "child",
                    "time": "09:30",
                    "timezone": "Europe/Kyiv",
                    "days_expression": "по будням",
                },
            }
        ],
    }
    before = deepcopy(value)
    view = fixture("ru").view("owner", now=NOW)
    commands = plans.materialize(value, view, "Поставь по будням на 09:30", NOW)
    assert commands[0]["payload"]["days"] == [0, 1, 2, 3, 4]
    assert "days_expression" not in commands[0]["payload"]
    assert value == before
    with pytest.raises(DomainError, match="invalid_alarm_days"):
        plans.materialize(value, view, "Поставь на выходные", NOW)
    value["commands"][0]["payload"]["days"] = [1, 2, 3, 4, 5]
    with pytest.raises(DomainError, match="invalid_alarm_days"):
        plans.materialize(value, view, "Поставь по будням на 09:30", NOW)


def test_grounding_normalizes_typography_without_translation_or_partial_word_matches():
    assert grounded_days("у п'ятницю", "Постав у п’ятницю о 08:00") == [4]
    assert grounded_days("по будням", "Постав ПО  БУДНЯМ на 08:00") == list(range(5))
    for expression, content in [("weekdays", "по будням"), ("среду", "средузы"), ("mon", "money")]:
        with pytest.raises(DomainError, match="invalid_alarm_days"):
            grounded_days(expression, content)


def test_literal_candidates_are_bounded_and_only_from_the_current_request():
    request = "Поставь по будням на 9.30, а по выходным на 10.30"
    assert day_expressions(request) == ["по будням", "по выходным"]
    for candidate in day_expressions("On Monday and Wednesday at 08:00"):
        assert candidate in "On Monday and Wednesday at 08:00"
        assert parse_days(candidate)
    assert "Monday and Wednesday" in day_expressions("On Monday and Wednesday at 08:00")
    assert "п’ятницю" in day_expressions("Постав у п’ятницю")
    assert not day_expressions("money")
    assert not day_expressions("Monday " * 65)
    assert not day_expressions("x" * 4097)
    assert not day_expressions(None)


def test_new_model_alarm_cannot_supply_numeric_days_but_clock_only_edit_preserves_current():
    view = fixture("ru").view("owner", now=NOW)
    payload = {"member": "child", "time": "08:00", "timezone": "Europe/Kyiv"}
    value = {"kind": "commands", "commands": [{"action": "alarms.save", "payload": payload}]}
    for days in (None, [1, 2, 3, 4, 5]):
        if days is not None:
            payload["days"] = days
        with pytest.raises(DomainError, match="invalid_alarm_days"):
            plans.materialize(value, view, "Поставь по будням на 08:00", NOW)
    view["alarms"] = [{"id": "A000001", "days": [0, 2], "revision": 4}]
    payload.update(id="A000001", days=[0, 2])
    result = plans.materialize(value, view, "Поставь этот будильник на 08:00", NOW)
    assert result[0]["payload"]["days"] == [0, 2]
    assert result[0]["payload"]["revision"] == 4
    payload.pop("days")
    assert plans.materialize(value, view, "На 08:00", NOW) == result
    payload["days"] = [1, 3]
    with pytest.raises(DomainError, match="invalid_alarm_days"):
        plans.materialize(value, view, "На 08:00", NOW)
