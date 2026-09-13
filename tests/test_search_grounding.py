"""Synthetic public queries through real parser, schema, Engine and search guards."""

import json
from copy import deepcopy

import pytest
from test_assistant import Provider, enable

from custom_components.family_assistant.assistant import plans
from custom_components.family_assistant.assistant.provider import Cascade
from custom_components.family_assistant.assistant.search_grounding import grounded_query
from custom_components.family_assistant.assistant.service import Assistant
from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.telegram.router import route

REQUEST = (
    "Найди в интернете официальный сайт Home Assistant и дай одну ссылку на него. "
    "Ничего в доме не меняй."
)


@pytest.mark.parametrize(
    "content,query,expected",
    [
        (REQUEST, "Home Assistant официальный сайт", "home assistant официальный сайт"),
        (REQUEST, "ОФИЦИАЛЬНЫЙ сайт Home\nAssistant", "официальный сайт home assistant"),
        (
            "Find the official website of Home Assistant.",
            "Home Assistant official website",
            "home assistant official website",
        ),
        (
            "Знайди офіційний сайт Home Assistant.",
            "Home Assistant офіційний сайт",
            "home assistant офіційний сайт",
        ),
        (
            "Search Home—Assistant documentation",
            "Home Assistant documentation",
            "home assistant documentation",
        ),
        ("Найди всё о берёзах", "все о березах", "все о березах"),
        ("Знайди все про п’єсу", "п'єсу", "п'єсу"),
        ("Find café hours", "cafe\u0301 hours", "café hours"),
        ("Search Home\u00a0Assistant", '"Home Assistant"', "home assistant"),
    ],
)
def test_only_benign_source_word_normalization_is_permitted(content, query, expected):
    assert grounded_query(query, content) == expected


@pytest.mark.parametrize(
    "content,query",
    [
        (REQUEST, "Home Assistant official website"),  # Translation is not lexical proof.
        (REQUEST, "Home Assistant official site hacked"),
        (REQUEST, "home-assistant.io"),
        ("Search plants", "plants medical records"),
        ("Search plants", "plant"),
        ("Search plants", "plants plants"),
        ("Search plants", "ants"),
        ("Search Home Assistant", "Home\u202e Assistant"),
        ("Search Home Assistant", "!!!"),
        ("Search T000001", "T000001"),
        ("Search T 000001", "T 000001"),
        ("Search L000001", "L000001"),
        ("Search https://example.org", "https://example.org"),
        ("Search somebody@example.org", "somebody@example.org"),
        ("Search somebody＠example.org", "somebody＠example.org"),
        ("Search 127.0.0.1", "127.0.0.1"),
        ("Search 127.0.0.1", "127 0 0 1"),
        ("Search fd00::1", "fd00::1"),
        ("Search plants", "p" * 301),
    ],
)
def test_new_concepts_identifiers_and_address_material_are_rejected(content, query):
    with pytest.raises(DomainError, match="search_query_not_grounded"):
        grounded_query(query, content)


@pytest.mark.parametrize(
    "query", ["Morgan Vale hobbies", "Vale Morgan hobbies", "morgan-v hobbies"]
)
def test_configured_names_and_explicit_aliases_cannot_be_reordered_to_evade_privacy(query):
    with pytest.raises(DomainError, match="search_query_not_grounded"):
        grounded_query(
            query,
            "Find Morgan Vale morgan-v hobbies",
            [
                {"name": "Morgan Vale", "aliases": ["morgan-v"]},
            ],
        )


class Search:
    def __init__(self):
        self.calls = []

    async def query(self, query, language, *, child=False):
        self.calls.append((query, language, child))
        return [
            {
                "url": "https://www.home-assistant.io/",
                "title": "Home Assistant",
                "snippet": "Public open-source home automation project.",
            }
        ]


async def test_real_route_and_typed_plan_accept_the_reported_public_query_without_mutation(
    engine, now
):
    await enable(engine, now)
    query = "Home Assistant официальный сайт"
    assert query.casefold() not in REQUEST.casefold()  # The previous guard rejected this.
    value = plans.validate({"kind": "search", "query": query})
    model = Provider(value, {"kind": "answer", "text": "Официальный сайт указан в источнике."})
    search = Search()
    assistant = Assistant(engine, Cascade([model], {}), search)
    before = deepcopy(engine.snapshot())
    answer = await route(engine, "owner", REQUEST, "public-search", now, fallback=assistant.respond)
    assert search.calls == [("home assistant официальный сайт", "en", False)]
    assert "https://www.home-assistant.io/" in answer
    assert engine.snapshot() == before
    assert "do not translate" in model.calls[0][0]["content"]
    assert len(model.calls) == 2


@pytest.mark.parametrize("actor", ["owner", "child"])
async def test_query_scope_and_child_search_flags_survive_normalization(engine, now, actor):
    await enable(engine, now)
    model = Provider(
        {"kind": "search", "query": "Assistant Home"}, {"kind": "answer", "text": "Public result."}
    )
    search = Search()
    await Assistant(engine, Cascade([model], {}), search).respond(
        actor, "Search Home Assistant", "safe-search", now
    )
    assert search.calls == [("assistant home", "en", actor == "child")]


async def test_model_cannot_search_names_or_quote_context_absent_from_current_request(engine, now):
    await enable(engine, now)
    for query in ("secret greenhouse", "Parent", "Home Assistant medical history"):
        model = Provider(*[{"kind": "search", "query": query}] * 2)
        search = Search()
        with pytest.raises(DomainError, match="search_query_not_grounded"):
            await Assistant(engine, Cascade([model], {}), search).respond(
                "owner",
                "Search Home Assistant",
                "untrusted-query",
                now,
                quoted_text="secret greenhouse medical history Parent",
            )
        assert search.calls == []
        assert len(model.calls) == 2
        assert json.loads(model.calls[1][1]["content"]) == {
            "current_request": "Search Home Assistant"
        }


async def test_translated_query_gets_one_current_text_only_repair_before_search(engine, now):
    await enable(engine, now)
    model = Provider(
        {"kind": "search", "query": "Home Assistant official website"},
        {"kind": "search", "query": "официальный сайт Home Assistant"},
        {"kind": "answer", "text": "Public source."},
    )
    search = Search()
    before = deepcopy(engine.snapshot())
    answer = await Assistant(engine, Cascade([model], {}), search).respond(
        "owner",
        REQUEST,
        "translated-search",
        now,
        quoted_text="PRIVATE_SYNTHETIC_QUOTE_NOT_FOR_REPAIR",
    )
    assert "https://www.home-assistant.io/" in answer
    assert search.calls == [("официальный сайт home assistant", "en", False)]
    assert len(model.calls) == 3
    repair = model.calls[1]
    assert json.loads(repair[1]["content"]) == {"current_request": REQUEST}
    assert "official website" not in json.dumps(repair)
    assert "PRIVATE_SYNTHETIC" not in json.dumps(repair)
    assert "do not translate" in repair[0]["content"].lower()
    assert engine.snapshot() == before


@pytest.mark.parametrize(
    "corrected",
    [
        {"kind": "search", "query": "Home Assistant official website"},
        {"kind": "search", "query": "Home Assistant household diagnosis"},
        {"kind": "commands", "operations": [{"action": "shopping.add", "payload": {"name": "x"}}]},
    ],
)
async def test_unproven_or_mutating_correction_never_reaches_search_or_engine(
    engine, now, corrected
):
    await enable(engine, now)
    model = Provider({"kind": "search", "query": "Home Assistant official website"}, corrected)
    search = Search()
    before = deepcopy(engine.snapshot())
    with pytest.raises(DomainError) as caught:
        await Assistant(engine, Cascade([model], {}), search).respond(
            "owner", REQUEST, "failed-repair", now
        )
    assert caught.value.code in {"search_query_not_grounded", "provider_bad_response"}
    assert search.calls == [] and len(model.calls) == 2
    assert engine.snapshot() == before


async def test_revocation_during_correction_prevents_search(engine, now):
    await enable(engine, now)
    allowed = True

    class RepairRevokingProvider(Provider):
        async def generate(self, messages, schema):
            nonlocal allowed
            if self.calls:
                allowed = False
            return await super().generate(messages, schema)

    def scope():
        if not allowed:
            raise DomainError("forbidden")

    model = RepairRevokingProvider(
        {"kind": "search", "query": "Home Assistant official website"},
        {"kind": "search", "query": "официальный сайт Home Assistant"},
    )
    search = Search()
    with pytest.raises(DomainError, match="forbidden"):
        await Assistant(engine, Cascade([model], {}), search).respond(
            "owner", REQUEST, "revoked-repair", now, scope_check=scope
        )
    assert len(model.calls) == 2 and search.calls == []


async def test_revoked_request_cannot_reach_external_search(engine, now):
    await enable(engine, now)
    allowed = True

    class RevokingProvider(Provider):
        async def generate(self, messages, schema):
            nonlocal allowed
            allowed = False
            return await super().generate(messages, schema)

    def scope():
        if not allowed:
            raise DomainError("forbidden")

    search = Search()
    model = RevokingProvider({"kind": "search", "query": "Assistant Home"})
    with pytest.raises(DomainError, match="forbidden"):
        await Assistant(engine, Cascade([model], {}), search).respond(
            "owner", "Search Home Assistant", "revoked-search", now, scope_check=scope
        )
    assert search.calls == []
