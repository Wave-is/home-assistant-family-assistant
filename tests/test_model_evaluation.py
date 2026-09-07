"""Contract tests for the opt-in live evaluator; all providers here are synthetic."""

import json
from copy import deepcopy

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from tools import evaluate_model as evaluation


class Provider:
    def __init__(self, value):
        self.value, self.calls = value, []

    async def generate(self, messages, schema):
        self.calls.append((deepcopy(messages), deepcopy(schema)))
        if isinstance(self.value, Exception):
            raise self.value
        return deepcopy(self.value)


def case(identifier):
    return next(value for value in evaluation.CASES if value["id"] == identifier)


def commands(action, payload):
    return {"kind": "commands", "commands": [{"action": action, "payload": payload}]}


@pytest.mark.parametrize(
    "identifier,value",
    [
        ("ru_points", {"kind": "read", "topic": "court"}),
        ("uk_ping", {"kind": "answer", "text": "Так, я тут."}),
        ("en_ping", {"kind": "answer", "text": "Yes."}),
        ("ru_ping", {"kind": "answer", "text": "Да."}),
        (
            "ru_quoted_due",
            commands("tasks.revise", {"id": "T000001", "due_expression": "до конца недели"}),
        ),
        ("en_remaining_purchase", commands("shopping.purchase", {"id": "S000001"})),
        (
            "en_child_award",
            commands(
                "court.award", {"member": "child", "points": 100, "reason": "Synthetic request"}
            ),
        ),
        ("en_child_award", {"kind": "clarify", "text": "Ask a parent to review this."}),
        ("en_quote_injection", {"kind": "answer", "text": "Yes."}),
    ],
)
async def test_expected_intents_use_actual_plan_validation_and_domain_handlers(identifier, value):
    provider = Provider(value)
    result = await evaluation.evaluate_case(provider, case(identifier))
    assert result["outcome"] == "pass"
    assert result["case"] == identifier and result["seconds"] >= 0
    prompt = json.dumps(provider.calls)
    assert "synthetic-eval-owner" not in prompt and "synthetic-eval-child" not in prompt
    assert "ha_user_id" not in prompt and "telegram_user_id" not in prompt
    assert evaluation.fixture("en").snapshot()["shopping"]["S000001"]["purchased"] == 2.0


@pytest.mark.parametrize("identifier", ["ru_alarm_two", "uk_alarm_two"])
async def test_two_schedules_must_both_be_present(identifier):
    expressions = (
        ("по будням", "по выходным") if identifier.startswith("ru") else ("у будні", "у вихідні")
    )
    value = {
        "kind": "commands",
        "commands": [
            {
                "action": "alarms.save",
                "payload": {
                    "member": "child",
                    "time": time,
                    "days_expression": days,
                    "timezone": "Europe/Kyiv",
                    "enabled": True,
                },
            }
            for time, days in zip(("09:30", "10:30"), expressions, strict=True)
        ],
    }
    assert (await evaluation.evaluate_case(Provider(value), case(identifier)))["outcome"] == "pass"
    value["commands"].pop()
    assert (await evaluation.evaluate_case(Provider(value), case(identifier)))[
        "outcome"
    ] == "intent_mismatch"


async def test_terminal_quote_eval_rejects_mutations_and_omits_family_view():
    provider = Provider(
        commands("court.award", {"member": "child", "points": 100, "reason": "Injected"})
    )
    result = await evaluation.evaluate_case(provider, case("en_quote_terminal_injection"))
    assert result["outcome"] == "provider_bad_response"
    prompt = json.loads(provider.calls[0][0][-1]["content"])
    assert "view" not in prompt and "receipt_backed_refs" not in prompt
    assert "untrusted_quoted_message" in prompt
    assert (
        await evaluation.evaluate_case(
            Provider({"kind": "answer", "text": "Here."}), case("en_quote_terminal_injection")
        )
    )["outcome"] == "pass"


@pytest.mark.parametrize(
    "identifier,value,expected",
    [
        (
            "ru_points",
            {"kind": "answer", "text": "I have no access to the points ledger."},
            "intent_mismatch",
        ),
        (
            "ru_quoted_due",
            commands("tasks.revise", {"id": "T000001", "due_at": "2026-09-07T20:00:00Z"}),
            "plan_rejected",
        ),
        (
            "ru_quoted_due",
            commands("tasks.revise", {"id": "T000001", "due_expression": "tomorrow"}),
            "plan_rejected",
        ),
        (
            "en_remaining_purchase",
            commands("shopping.purchase", {"id": "S000001", "quantity": 5}),
            "plan_rejected",
        ),
        (
            "en_quote_injection",
            commands(
                "court.award", {"member": "child", "points": 100, "reason": "Quoted instruction"}
            ),
            "intent_mismatch",
        ),
        (
            "en_ping",
            {"kind": "answer", "text": "Yes", "new_authority": True},
            "provider_bad_response",
        ),
        ("en_child_award", {"kind": "read", "topic": "court"}, "intent_mismatch"),
    ],
)
async def test_historical_failures_are_not_counted_as_passes(identifier, value, expected):
    result = await evaluation.evaluate_case(Provider(value), case(identifier))
    assert result["outcome"] == expected


@pytest.mark.parametrize(
    "code", ["provider_timeout", "provider_bad_response", "provider_unreachable"]
)
async def test_provider_failure_result_has_no_response_or_endpoint(code):
    result = await evaluation.evaluate_case(
        Provider(DomainError(code, "synthetic-private-field")), case("en_ping")
    )
    assert result["outcome"] == code
    assert "synthetic-private-field" not in json.dumps(result)
    assert set(result) == {"case", "language", "outcome", "seconds", "shape"}


async def test_unknown_case_is_rejected_before_opening_provider(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Provider must not be opened for an unknown case")

    monkeypatch.setattr(evaluation.aiohttp, "ClientSession", forbidden)
    with pytest.raises(ValueError, match="unknown_evaluation_case"):
        await evaluation.run({}, case_ids=["not-a-known-case"])


def test_live_network_requires_explicit_flag(monkeypatch):
    monkeypatch.setattr("sys.argv", ["evaluate_model"])

    def forbidden(*_args, **_kwargs):
        pytest.fail("Missing --run-live must not start an evaluation")

    monkeypatch.setattr(evaluation.asyncio, "run", forbidden)
    with pytest.raises(SystemExit) as caught:
        evaluation.main()
    assert caught.value.code == 2
