"""Bind native flows to their actual HTTP caller or explicit internal context."""

from .domain.validation import DomainError


def user_id(flow):
    """Core's native flow HTTP endpoints do not populate context.user_id.

    Resolve the authenticated request instead of selecting an arbitrary HA
    administrator. Keep the identity pinned across subsequent form requests.
    Programmatically initialized flows may supply an explicit trusted context.
    """
    context = getattr(flow, "context", None)
    if not isinstance(context, dict):
        raise DomainError("forbidden")
    pinned = context.get("user_id")
    request = None
    try:
        from homeassistant.helpers.http import current_request

        request = current_request.get()
    except (ImportError, LookupError):
        pass
    if request is not None:
        user = request.get("hass_user")
        if user is None or getattr(user, "is_active", False) is not True:
            raise DomainError("forbidden")
        actual = getattr(user, "id", None)
        if pinned is not None and pinned != actual:
            raise DomainError("forbidden")
        pinned = actual
    if not isinstance(pinned, str) or not pinned:
        raise DomainError("forbidden")
    context["user_id"] = pinned
    return pinned
