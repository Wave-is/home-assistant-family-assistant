"""Bounded shared-shopping assignments and presentation-only buyer filters."""

import re

from ..domain.validation import DomainError
from .creation import shopping_details

ASSIGN = re.compile(
    r"^(?:(?:поручи|попроси)\s+(.{1,80}?)\s+купить\s+(.+)|"
    r"(?:доручи|попроси)\s+(.{1,80}?)\s+купити\s+(.+)|"
    r"(?:ask|assign)\s+(.{1,80}?)\s+to\s+buy\s+(.+))$",
    re.I,
)
SET_BUYER = re.compile(
    r"^(?:(?:назначь|смени|измени)\s+покупателя|"
    r"(?:признач|зміни)\s+покупця|(?:assign|change)\s+buyer)\s+"
    r"(S\d{6,})\s+(?:(?:на|to)\s+)?(.+)$",
    re.I,
)
CLEAR_BUYER = re.compile(
    r"^(?:сними\s+покупателя|убери\s+покупателя|зніми\s+покупця|"
    r"прибери\s+покупця|unassign\s+buyer|remove\s+buyer)\s+(S\d{6,})$",
    re.I,
)
SCOPED = re.compile(
    r"^(?:(?:покажи\s+)?покупки|(?:покажи\s+)?закупи|"
    r"(?:show\s+)?shopping)\s+(?:(?:для|for)\s+)?(.+)$",
    re.I,
)
MINE = {"мои покупки", "мої покупки", "my shopping", "mine", "мои", "мої", "me"}


def assignment_match(content):
    match = ASSIGN.fullmatch(content.strip())
    if match is not None:
        recipient = next(match[index] for index in (1, 3, 5) if match[index] is not None)
        if re.search(r"\b(?:task|задач[ауыеи]|завдання)\b", recipient, re.I):
            return None  # Explicit task wording belongs to the ordinary task parser.
    return match


def assignment_recipient(content):
    match = assignment_match(content)
    if match is None:
        return None
    group = next(index for index in (1, 3, 5) if match[index] is not None)
    start, end = match.span(group)
    offset = len(content) - len(content.lstrip())
    return start + offset, end + offset


def buyer_member(state, view, value):
    from .intents import find_member, normalize

    if view["role"] == "guest":
        raise DomainError("forbidden")
    member_id = view["actor"] if normalize(value) in MINE else find_member(state, value)
    if state["members"][member_id]["role"] == "guest":
        raise DomainError("invalid_field", "buyer")
    return member_id


def edit_buyer(state, view, item_id, value):
    """Freeze the existing full edit contract; never clone or reset a purchase."""
    item = next((row for row in view["shopping"] if row["id"] == item_id.upper()), None)
    if item is None:
        raise DomainError("not_found")
    buyer = buyer_member(state, view, value) if value is not None else None
    payload = {
        "id": item["id"],
        "revision": item["revision"],
        "name": item["name"],
        **{field: item.get(field, "") for field in ("category", "store", "note")},
        "buyer": buyer,
    }
    if "barcode" in item:
        payload["barcode"] = item["barcode"]
    if buyer is not None:
        payload["buyer_revision"] = state["members"][buyer]["revision"]
    return payload


def parse(state, view, content):
    from .intents import normalize

    value = content.strip()
    if normalize(value) in {"мои покупки", "мої покупки", "my shopping"}:
        return "read.shopping", {"buyer": buyer_member(state, view, "mine")}
    if match := SCOPED.fullmatch(value.strip(" .?!")):
        return "read.shopping", {"buyer": buyer_member(state, view, match[1])}
    if match := assignment_match(value):
        group = next(index for index in (1, 3, 5) if match[index] is not None)
        if re.search(
            r"\b(?:поручи|попроси|доручи|ask|assign)\s+.+\s+(?:купить|купити|to\s+buy)\b",
            match[group + 1],
            re.I,
        ):
            raise DomainError("ambiguous_command")  # One assignment per request, not a batch.
        buyer = buyer_member(state, view, match[group])
        return "shopping.add", {
            **shopping_details(match[group + 1]),
            "buyer": buyer,
            "buyer_revision": state["members"][buyer]["revision"],
        }
    if match := SET_BUYER.fullmatch(value):
        return "shopping.edit", edit_buyer(state, view, match[1], match[2])
    if match := CLEAR_BUYER.fullmatch(value):
        return "shopping.edit", edit_buyer(state, view, match[1], None)
    return None
