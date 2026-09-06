"""Bounded read-only access to an explicitly configured Mealie v3 server."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from ..assistant.http import endpoint, request_json
from ..domain.validation import DomainError

_VERSION = re.compile(r"^v?(?P<major>[0-9]+)(?:\.[0-9]+){1,2}(?:[-+][0-9A-Za-z.-]+)?$")
_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,248}[a-z0-9])?$")
_PAGINATION_FIELDS = frozenset(
    {"page", "per_page", "total", "total_pages", "items", "next", "previous"}
)


def _bad_response() -> DomainError:
    return DomainError("provider_bad_response")


def _strict_int(value, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _bad_response()
    return value


def _required_text(value, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise _bad_response()
    return value.strip()


def _optional_text(value, maximum: int) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        return None
    return value.strip()


def _flag(value) -> bool:
    if value is None:
        return False
    if type(value) is not bool:
        raise _bad_response()
    return value


def _finite_number(value) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and (isinstance(value, int) or math.isfinite(value))
    )


def _slug(value, *, external: bool = False) -> str:
    try:
        value = _required_text(value, 250)
    except DomainError:
        if external:
            raise DomainError("invalid_field", "slug") from None
        raise
    if not _SLUG.fullmatch(value):
        if external:
            raise DomainError("invalid_field", "slug")
        raise _bad_response()
    return value


def _page(data: dict, *, requested_page: int, per_page: int) -> tuple[int, int, list]:
    if not _PAGINATION_FIELDS <= data.keys():
        raise _bad_response()
    page = _strict_int(data["page"], minimum=1, maximum=1000)
    actual_per_page = _strict_int(data["per_page"], minimum=1, maximum=1000)
    _strict_int(data["total"], minimum=0, maximum=2**53 - 1)
    total_pages = _strict_int(data["total_pages"], minimum=0, maximum=2**53 - 1)
    items = data["items"]
    if (
        page != requested_page
        or actual_per_page != per_page
        or not isinstance(items, list)
        or len(items) > per_page
    ):
        raise _bad_response()
    for guide in (data["next"], data["previous"]):
        if guide is not None and (not isinstance(guide, str) or len(guide) > 2048):
            raise _bad_response()
    return page, total_pages, items


def _summary(value) -> dict:
    if not isinstance(value, dict):
        raise _bad_response()
    return {
        "id": _required_text(value.get("id"), 128),
        "slug": _slug(value.get("slug")),
        "name": _required_text(value.get("name"), 120),
    }


def _quantity(value) -> tuple[float | None, str | None]:
    if value is None or (
        not isinstance(value, bool) and isinstance(value, (int, float)) and value == 0
    ):
        return None, "missing_quantity"
    if not _finite_number(value):
        return None, "invalid_quantity"
    try:
        decimal = Decimal(str(value))
    except InvalidOperation:
        return None, "invalid_quantity"
    if decimal <= 0 or decimal > 1_000_000 or decimal != decimal.quantize(Decimal("0.001")):
        return None, "invalid_quantity"
    return float(decimal), None


def _source_servings(data: dict) -> tuple[dict, bool]:
    raw = data.get("recipeServings")
    value = None
    if _finite_number(raw) and (isinstance(raw, int) or raw.is_integer()) and 1 <= raw <= 50:
        value = int(raw)

    display = ""
    if _finite_number(raw) and raw > 0:
        display = str(int(raw)) if isinstance(raw, int) or raw.is_integer() else str(raw)
    else:
        yield_quantity = data.get("recipeYieldQuantity")
        yield_name = data.get("recipeYield")
        parts = []
        if _finite_number(yield_quantity) and yield_quantity > 0:
            parts.append(
                str(int(yield_quantity))
                if isinstance(yield_quantity, int) or yield_quantity.is_integer()
                else str(yield_quantity)
            )
        if yield_name is not None:
            if not isinstance(yield_name, str) or len(yield_name) > 120:
                raise _bad_response()
            if yield_name.strip():
                parts.append(yield_name.strip())
        display = " ".join(parts)
    if len(display) > 120:
        raise _bad_response()
    return {"value": value, "display": display}, value is None


def _ingredient(value, *, disable_amount: bool) -> dict:
    if not isinstance(value, dict):
        raise _bad_response()
    display = value.get("display", "")
    if not isinstance(display, str) or len(display) > 500:
        raise _bad_response()

    referenced = value.get("referencedRecipe") is not None
    row_disabled = _flag(value.get("disableAmount"))
    manual = disable_amount or row_disabled
    if referenced:
        return {
            "display": display,
            "name": None,
            "unit": None,
            "quantity": None,
            "blockers": ["unsupported_reference"],
        }

    food = value.get("food")
    unit_data = value.get("unit")
    if food is not None and not isinstance(food, dict):
        raise _bad_response()
    if unit_data is not None and not isinstance(unit_data, dict):
        raise _bad_response()
    name = _optional_text(food.get("name") if food else None, 120)
    blockers = []
    if name is None:
        blockers.append("missing_name")

    if manual:
        unit = None
        quantity = None
        blockers.append("manual_units")
    else:
        unit = _optional_text(unit_data.get("name") if unit_data else None, 24)
        if unit is None:
            blockers.append("missing_unit")
        quantity, quantity_blocker = _quantity(value.get("quantity"))
        if quantity_blocker:
            blockers.append(quantity_blocker)
    return {
        "display": display,
        "name": name,
        "unit": unit,
        "quantity": quantity,
        "blockers": blockers,
    }


class Mealie:
    """A GET-only Mealie v3 client; returned content is an untrusted review candidate."""

    def __init__(self, session, config):
        if not isinstance(config, dict):
            raise DomainError("invalid_field", "config")
        allow_http = config.get("allow_http", False)
        if type(allow_http) is not bool:
            raise DomainError("invalid_field", "allow_http")
        self.url = endpoint(config.get("url"), allow_http=allow_http)
        token = config.get("token")
        if (
            not isinstance(token, str)
            or not token
            or token != token.strip()
            or len(token) > 4096
            or "\r" in token
            or "\n" in token
        ):
            raise DomainError("invalid_field", "token")
        timeout = config.get("timeout", 15)
        if type(timeout) is not int or not 5 <= timeout <= 30:
            raise DomainError("invalid_field", "timeout")
        self.session = session
        self.timeout = timeout
        self.headers = {"Authorization": f"Bearer {token}"}

    async def _list(self, query: str, page: int, per_page: int) -> tuple[int, int, list]:
        params = {"page": page, "perPage": per_page}
        if query:
            params["search"] = query
        data = await request_json(
            self.session,
            "GET",
            self.url + "/api/recipes",
            timeout=self.timeout,
            headers=self.headers,
            params=params,
        )
        return _page(data, requested_page=page, per_page=per_page)

    async def inspect(self) -> dict:
        about = await request_json(
            self.session,
            "GET",
            self.url + "/api/app/about",
            timeout=self.timeout,
        )
        version = about.get("version")
        if not isinstance(version, str) or len(version) > 64:
            raise _bad_response()
        match = _VERSION.fullmatch(version)
        if not match or int(match.group("major")) != 3:
            raise DomainError("provider_bad_response")
        _, _, items = await self._list("", 1, 1)
        for item in items:
            _summary(item)
        return {"version": version}

    async def search(self, query, page=1) -> dict:
        if not isinstance(query, str) or len(query) > 120:
            raise DomainError("invalid_field", "query")
        if type(page) is not int or not 1 <= page <= 1000:
            raise DomainError("invalid_field", "page")
        result_page, total_pages, items = await self._list(query.strip(), page, 10)
        return {
            "page": result_page,
            "total_pages": total_pages,
            "items": [_summary(item) for item in items],
        }

    async def recipe(self, slug) -> dict:
        slug = _slug(slug, external=True)
        data = await request_json(
            self.session,
            "GET",
            self.url + "/api/recipes/" + quote(slug, safe=""),
            timeout=self.timeout,
            headers=self.headers,
        )
        source = _summary(data)
        if source["slug"] != slug:
            raise _bad_response()
        servings, missing_servings = _source_servings(data)
        ingredients = data.get("recipeIngredient")
        if not isinstance(ingredients, list) or len(ingredients) > 100:
            raise _bad_response()
        settings = data.get("settings")
        if settings is not None and not isinstance(settings, dict):
            raise _bad_response()
        disable_amount = _flag(settings.get("disableAmount") if settings else None)
        blockers = []
        if missing_servings:
            blockers.append("servings_required")
        if len(ingredients) > 20:
            blockers.append("too_many_ingredients")
        return {
            "source": {"provider": "mealie", "id": source["id"], "slug": source["slug"]},
            "title": source["name"],
            "source_servings": servings,
            "ingredients": [
                _ingredient(ingredient, disable_amount=disable_amount) for ingredient in ingredients
            ],
            "blockers": blockers,
        }
