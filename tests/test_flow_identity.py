"""Native REST flow identity is real request identity, not a guessed owner."""

from contextvars import ContextVar
from types import ModuleType, SimpleNamespace

import pytest

from custom_components.family_assistant.domain.validation import DomainError
from custom_components.family_assistant.flow_identity import user_id


@pytest.fixture
def request_context(monkeypatch):
    module = ModuleType("homeassistant.helpers.http")
    module.current_request = ContextVar("synthetic_request", default=None)
    monkeypatch.setitem(__import__("sys").modules, module.__name__, module)
    return module.current_request


def test_native_request_supplies_missing_context_and_pins_caller(request_context):
    flow = SimpleNamespace(context={})
    request_context.set({"hass_user": SimpleNamespace(id="actual-caller", is_active=True)})
    assert user_id(flow) == "actual-caller"
    assert flow.context == {"user_id": "actual-caller"}
    request_context.set({"hass_user": SimpleNamespace(id="another-admin", is_active=True)})
    with pytest.raises(DomainError, match="forbidden"):
        user_id(flow)


def test_missing_or_inactive_caller_never_substitutes_an_owner(request_context):
    with pytest.raises(DomainError, match="forbidden"):
        user_id(SimpleNamespace(context={}))
    request_context.set({"hass_user": SimpleNamespace(id="disabled", is_active=False)})
    with pytest.raises(DomainError, match="forbidden"):
        user_id(SimpleNamespace(context={"user_id": "disabled"}))


def test_explicit_internal_flow_context_remains_supported(request_context):
    assert user_id(SimpleNamespace(context={"user_id": "authenticated-internal-caller"})) == (
        "authenticated-internal-caller"
    )
