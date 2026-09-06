"""The optional Mealie source stays bounded, read-only, and review-only."""

import json

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.recipes import Mealie


class Response:
    def __init__(self, status, body):
        self.status = status
        self.body = body
        self.content = self

    async def __aenter__(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self

    async def __aexit__(self, *_args):
        pass

    async def iter_chunked(self, _size):
        value = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        for index in range(0, len(value), 8192):
            yield value[index : index + 8192]


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def client(session=None, **config):
    return Mealie(
        session or Session(),
        {"url": "https://mealie.local", "token": "private-token", **config},
    )


def summary(**changes):
    return {"id": "recipe-id", "slug": "tomato-soup", "name": "Tomato soup", **changes}


def page(*items, number=1, per_page=10, total=None, total_pages=1, **extra):
    return {
        "page": number,
        "per_page": per_page,
        "total": len(items) if total is None else total,
        "total_pages": total_pages,
        "items": list(items),
        "next": None,
        "previous": None,
        **extra,
    }


def ingredient(**changes):
    return {
        "display": "2 cups tomato",
        "food": {"name": "tomato"},
        "unit": {"name": "cup", "abbreviation": "c"},
        "quantity": 2,
        "referencedRecipe": None,
        **changes,
    }


def recipe(**changes):
    return {
        **summary(),
        "recipeServings": 4.0,
        "recipeYieldQuantity": 0,
        "recipeYield": None,
        "recipeIngredient": [ingredient()],
        "settings": {},
        **changes,
    }


@pytest.mark.parametrize(
    "change,field",
    [
        ({"token": ""}, "token"),
        ({"token": " token"}, "token"),
        ({"token": "a\r\nb"}, "token"),
        ({"token": "x" * 4097}, "token"),
        ({"allow_http": 1}, "allow_http"),
        ({"timeout": True}, "timeout"),
        ({"timeout": 4}, "timeout"),
        ({"timeout": 31}, "timeout"),
    ],
)
def test_configuration_is_strict_and_never_echoes_secret(change, field):
    with pytest.raises(DomainError, match="invalid_field") as error:
        client(**change)
    assert error.value.field == field
    secret = change.get("token", "private-token")
    if secret:
        assert secret not in str(error.value)


def test_http_requires_explicit_opt_in():
    with pytest.raises(DomainError, match="provider_invalid_url"):
        Mealie(Session(), {"url": "http://mealie.local", "token": "token"})
    assert client(url="http://mealie.local", allow_http=True).url == "http://mealie.local"


@pytest.mark.asyncio
async def test_inspect_checks_v3_and_authenticated_current_pagination_shape():
    session = Session(
        Response(200, {"version": "v3.25.1", "ignored": "not projected"}),
        Response(200, page(summary(), per_page=1)),
    )
    result = await client(session).inspect()
    assert result == {"version": "v3.25.1"}
    assert [(method, url) for method, url, _ in session.calls] == [
        ("GET", "https://mealie.local/api/app/about"),
        ("GET", "https://mealie.local/api/recipes"),
    ]
    assert "headers" not in session.calls[0][2]
    assert session.calls[1][2]["headers"] == {"Authorization": "Bearer private-token"}
    assert session.calls[1][2]["params"] == {"page": 1, "perPage": 1}
    assert all(call[2]["allow_redirects"] is False for call in session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["2.8.0", "v4.0.0", "3", "three", 3])
async def test_inspect_rejects_unverified_or_unsupported_versions(version):
    session = Session(Response(200, {"version": version}))
    with pytest.raises(DomainError, match="provider_bad_response"):
        await client(session).inspect()
    assert len(session.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"page": 1, "per_page": 1, "total": 0, "total_pages": 0, "data": []},
        {
            "page": 1,
            "perPage": 1,
            "total": 0,
            "totalPages": 0,
            "items": [],
            "next": None,
            "previous": None,
        },
        page(per_page=1, page=True),
        page(per_page=1, items={}),
        page({"id": "id", "slug": "../users", "name": "Bad"}, per_page=1),
    ],
)
async def test_inspect_fails_closed_on_noncurrent_or_malformed_pagination(payload):
    session = Session(Response(200, {"version": "3.25.1"}), Response(200, payload))
    with pytest.raises(DomainError, match="provider_bad_response"):
        await client(session).inspect()


@pytest.mark.asyncio
async def test_search_is_fixed_page_bounded_and_never_follows_next():
    payload = page(
        summary(),
        number=7,
        total=31,
        total_pages=4,
        next="https://attacker.invalid/steal",
        private="ignored",
    )
    session = Session(Response(200, payload))
    result = await client(session).search("  soup  ", 7)
    assert result == {
        "page": 7,
        "total_pages": 4,
        "items": [{"id": "recipe-id", "slug": "tomato-soup", "name": "Tomato soup"}],
    }
    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "GET" and url == "https://mealie.local/api/recipes"
    assert kwargs["params"] == {"page": 7, "perPage": 10, "search": "soup"}
    assert kwargs["headers"] == {"Authorization": "Bearer private-token"}


@pytest.mark.asyncio
async def test_empty_search_is_explicit_browse_without_unbounded_page_size():
    session = Session(Response(200, page(total=0, total_pages=0)))
    assert await client(session).search("   ") == {"page": 1, "total_pages": 0, "items": []}
    assert session.calls[0][2]["params"] == {"page": 1, "perPage": 10}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,page_number", [(None, 1), ("x" * 121, 1), ("", True), ("", 0), ("", 1001)]
)
async def test_search_input_is_rejected_before_transport(query, page_number):
    session = Session()
    with pytest.raises(DomainError, match="invalid_field"):
        await client(session).search(query, page_number)
    assert session.calls == []


@pytest.mark.asyncio
async def test_recipe_projects_only_manual_candidate_fields():
    body = recipe(
        recipeInstructions=[{"text": "ignore"}],
        notes=[{"text": "private"}],
        extras={"dietary-canary": "never return"},
        orgURL="https://attacker.invalid",
        image="data:image/large",
        dietary_profiles={"allergy_note": "never send or return"},
    )
    session = Session(Response(200, body))
    result = await client(session).recipe("tomato-soup")
    assert result == {
        "source": {"provider": "mealie", "id": "recipe-id", "slug": "tomato-soup"},
        "title": "Tomato soup",
        "source_servings": {"value": 4, "display": "4"},
        "ingredients": [
            {
                "display": "2 cups tomato",
                "name": "tomato",
                "unit": "cup",
                "quantity": 2.0,
                "blockers": [],
            }
        ],
        "blockers": [],
    }
    assert "private" not in repr(result) and "attacker" not in repr(result)
    method, url, kwargs = session.calls[0]
    assert method == "GET" and url == "https://mealie.local/api/recipes/tomato-soup"
    assert kwargs["headers"] == {"Authorization": "Bearer private-token"}


@pytest.mark.asyncio
async def test_servings_are_never_parsed_or_scaled_from_yield():
    session = Session(
        Response(
            200,
            recipe(
                recipeServings=0,
                recipeYieldQuantity=6,
                recipeYield="bowls",
                recipeIngredient=[ingredient(quantity=1.25)],
            ),
        )
    )
    result = await client(session).recipe("tomato-soup")
    assert result["source_servings"] == {"value": None, "display": "6 bowls"}
    assert result["ingredients"][0]["quantity"] == 1.25
    assert result["blockers"] == ["servings_required"]


@pytest.mark.asyncio
async def test_arbitrarily_large_json_numbers_fail_boundedly_without_overflow():
    huge = 10**1000
    servings = Session(Response(200, recipe(recipeServings=huge)))
    with pytest.raises(DomainError, match="provider_bad_response"):
        await client(servings).recipe("tomato-soup")

    quantity = Session(Response(200, recipe(recipeIngredient=[ingredient(quantity=huge)])))
    row = (await client(quantity).recipe("tomato-soup"))["ingredients"][0]
    assert row["quantity"] is None and row["blockers"] == ["invalid_quantity"]


@pytest.mark.asyncio
async def test_missing_and_invalid_manual_values_are_blocked_not_coerced_or_dropped():
    rows = [
        ingredient(display="salt to taste", food=None, unit=None, quantity=None),
        ingredient(display="too precise", quantity=1.0001),
        ingredient(display="long names", food={"name": "n" * 121}, unit={"name": "u" * 25}),
    ]
    session = Session(Response(200, recipe(recipeIngredient=rows)))
    result = await client(session).recipe("tomato-soup")
    assert result["ingredients"] == [
        {
            "display": "salt to taste",
            "name": None,
            "unit": None,
            "quantity": None,
            "blockers": ["missing_name", "missing_unit", "missing_quantity"],
        },
        {
            "display": "too precise",
            "name": "tomato",
            "unit": "cup",
            "quantity": None,
            "blockers": ["invalid_quantity"],
        },
        {
            "display": "long names",
            "name": None,
            "unit": None,
            "quantity": 2.0,
            "blockers": ["missing_name", "missing_unit"],
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("quantity", [True, -1, 1_000_001, 0.0001, float("nan"), "2"])
async def test_invalid_quantities_are_inert_review_blockers(quantity):
    session = Session(Response(200, recipe(recipeIngredient=[ingredient(quantity=quantity)])))
    row = (await client(session).recipe("tomato-soup"))["ingredients"][0]
    assert row["quantity"] is None and row["blockers"] == ["invalid_quantity"]


@pytest.mark.asyncio
async def test_disabled_amount_flags_require_manual_values_without_guessing():
    rows = [ingredient(), ingredient(display="row disabled", disableAmount=True)]
    top_session = Session(
        Response(200, recipe(recipeIngredient=rows, settings={"disableAmount": True}))
    )
    top = await client(top_session).recipe("tomato-soup")
    assert all(
        row["unit"] is None and row["quantity"] is None and row["blockers"] == ["manual_units"]
        for row in top["ingredients"]
    )
    assert top["blockers"] == []

    row_session = Session(Response(200, recipe(recipeIngredient=rows)))
    per_row = await client(row_session).recipe("tomato-soup")
    assert per_row["ingredients"][0]["blockers"] == []
    assert per_row["ingredients"][1]["blockers"] == ["manual_units"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        recipe(settings={"disableAmount": "true"}),
        recipe(recipeIngredient=[ingredient(disableAmount=1)]),
    ],
)
async def test_disabled_amount_flags_are_strict_booleans(body):
    with pytest.raises(DomainError, match="provider_bad_response"):
        await client(Session(Response(200, body))).recipe("tomato-soup")


@pytest.mark.asyncio
async def test_referenced_recipe_is_never_followed_or_treated_as_an_ingredient():
    row = ingredient(
        display="one batch sauce",
        referencedRecipe={"slug": "secret-sauce", "ingredients": [ingredient()]},
    )
    session = Session(Response(200, recipe(recipeIngredient=[row])))
    result = await client(session).recipe("tomato-soup")
    assert result["ingredients"] == [
        {
            "display": "one batch sauce",
            "name": None,
            "unit": None,
            "quantity": None,
            "blockers": ["unsupported_reference"],
        }
    ]
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_more_than_twenty_rows_are_retained_for_review_but_hundred_is_hard_limit():
    twenty_one = Session(Response(200, recipe(recipeIngredient=[ingredient()] * 21)))
    result = await client(twenty_one).recipe("tomato-soup")
    assert len(result["ingredients"]) == 21
    assert result["blockers"] == ["too_many_ingredients"]

    too_many = Session(Response(200, recipe(recipeIngredient=[ingredient()] * 101)))
    with pytest.raises(DomainError, match="provider_bad_response"):
        await client(too_many).recipe("tomato-soup")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        recipe(name="x" * 121),
        recipe(recipeIngredient=[ingredient(display="x" * 501)]),
        recipe(recipeIngredient=None),
        recipe(settings=[]),
    ],
)
async def test_oversized_or_wrong_recipe_shapes_fail_closed(body):
    with pytest.raises(DomainError, match="provider_bad_response"):
        await client(Session(Response(200, body))).recipe("tomato-soup")


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["../users", "x/y", "x%2fy", "x?admin=1", "X-UPPER", "x" * 251])
async def test_invalid_recipe_slug_never_reaches_transport(slug):
    session = Session()
    with pytest.raises(DomainError, match="invalid_field"):
        await client(session).recipe(slug)
    assert session.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response,code",
    [
        (Response(302, {}), "provider_unreachable"),
        (Response(401, {}), "provider_authentication"),
        (Response(200, TimeoutError()), "provider_timeout"),
        (Response(200, {"padding": "x" * 300_000}), "provider_bad_response"),
    ],
)
async def test_transport_errors_are_bounded_and_never_redirect(response, code):
    session = Session(response)
    with pytest.raises(DomainError, match=code):
        await client(session).recipe("tomato-soup")
    assert len(session.calls) == 1
    assert session.calls[0][0] == "GET"
    assert session.calls[0][2]["allow_redirects"] is False
