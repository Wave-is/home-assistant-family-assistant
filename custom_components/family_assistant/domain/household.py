"""Generic opt-in family templates and validated household time zone."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .validation import DomainError, enum

TEMPLATES = ("manual", "pair", "parents_children", "single_parent")
NAMES = {
    "en": {"owner": "Owner", "adult": "Partner", "parent": "Parent 2", "child": "Child 1"},
    "ru": {"owner": "Владелец", "adult": "Партнёр", "parent": "Родитель 2", "child": "Ребёнок 1"},
    "uk": {"owner": "Власник", "adult": "Партнер", "parent": "Батьки 2", "child": "Дитина 1"},
}


def timezone(value):
    if not isinstance(value, str) or len(value) > 80:
        raise DomainError("invalid_field", "timezone")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise DomainError("invalid_field", "timezone") from None
    return value


def apply_template(state, template):
    """Only called when a brand-new household is created, never on update."""
    enum(template, TEMPLATES, "template")
    roles = {
        "manual": (),
        "pair": ("adult",),
        "parents_children": ("parent", "child"),
        "single_parent": ("child",),
    }[template]
    language = state["settings"]["language"]
    for index, role in enumerate(roles, 1):
        member_id = f"M{index:06}"
        state["members"][member_id] = {
            "id": member_id,
            "name": NAMES[language][role],
            "role": role,
            "language": language,
            "active": True,
            "revision": 1,
            "ha_user_id": None,
            "aliases": [],
        }
    state["sequences"]["M"] = len(roles)
