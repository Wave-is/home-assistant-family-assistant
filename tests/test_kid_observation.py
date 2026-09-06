"""Configured access summaries never turn stale or pending state into success."""

from copy import deepcopy
from datetime import timedelta

import pytest
from test_kids import Router, binding, plan, prepare_engine

from custom_components.family_assistant.domain.engine import new_state
from custom_components.family_assistant.network import kids
from custom_components.family_assistant.network.kid_observation import status


def fixture(now):
    router = Router(now)
    state = new_state("synthetic-owner", "Test", modules=["mikrotik"])
    state["network"] = {
        "backend": "synthetic",
        "tables": router.tables,
        "inventory": {"observed_at": now.isoformat()},
        "kid_plans": {},
    }
    return state, router, binding(router)


def project(state, router, bound, now):
    return status(state, bound, kids.profile(router.tables["kids"][0]), now)


def observe(state, router, now):
    state["network"]["inventory"]["observed_at"] = now.isoformat()
    router.tables["clock"][0].update(date=now.strftime("%Y-%m-%d"), time=now.strftime("%H:%M:%S"))


def temporary(state, router, now, mode="grant", **kwargs):
    p = plan(router, now, mode, minutes=30, **kwargs)
    p.update(status="applied", progress={"phase": "verified", "timer_verified": True})
    state["network"]["kid_plans"][p["id"]] = p
    router.tables["kids"][0].update(p["after"])
    return p


def test_fresh_schedule_and_no_mutation(now):
    state, router, bound = fixture(now)
    previous = deepcopy(state)
    result = project(state, router, bound, now)
    assert result["allows"] is True and result["mode"] == "schedule"
    assert result["remaining_minutes"] == 14 * 60
    assert result["next_change_at"] == now.replace(hour=22).isoformat()
    assert result["next_allows"] is False
    assert result["valid_until"] == (now + timedelta(minutes=3)).isoformat()
    assert state == previous


@pytest.mark.parametrize("delta", [timedelta(minutes=3, microseconds=1), -timedelta(seconds=1)])
def test_stale_or_future_observation_is_unknown(now, delta):
    state, router, bound = fixture(now)
    result = project(state, router, bound, now + delta)
    assert result["mode"] == "unknown" and result["reason"] == "stale"
    assert all(result[k] is None for k in ("allows", "remaining_minutes", "valid_until"))


@pytest.mark.parametrize("case", ["missing", "bad_clock", "wrong_zone", "module_off", "tur"])
def test_unverified_or_unmodeled_observations(now, case):
    state, router, bound = fixture(now)
    if case == "missing":
        state["network"]["inventory"] = {}
    elif case == "bad_clock":
        router.tables["clock"][0]["time"] = "00:00:00"
    elif case == "wrong_zone":
        router.tables["clock"][0]["time-zone-name"] = "Europe/London"
    elif case == "module_off":
        state["settings"]["modules"] = []
    else:
        router.tables["kids"][0]["tur-sun"] = "08:00-10:00"
    assert project(state, router, bound, now)["mode"] == "unknown"


def test_expired_grant_needs_fresh_restoration_evidence(now):
    state, router, bound = fixture(now)
    p = temporary(state, router, now)
    deadline = now + timedelta(minutes=30)
    observe(state, router, deadline)
    assert project(state, router, bound, deadline)["reason"] == "expiry_pending"
    router.tables["kids"][0].update(p["before"])
    assert project(state, router, bound, deadline)["mode"] == "schedule"
    assert project(state, router, bound, deadline)["temporary_until"] is None
    observe(state, router, deadline - timedelta(seconds=1))
    assert project(state, router, bound, deadline)["reason"] == "expiry_pending"


def test_grant_restoring_open_schedule_uses_later_real_closure(now):
    state, router, bound = fixture(now)
    temporary(state, router, now)
    result = project(state, router, bound, now)
    assert result["temporary_mode"] == "grant"
    assert result["temporary_until"] == (now + timedelta(minutes=30)).isoformat()
    assert result["next_change_at"] == now.replace(hour=22).isoformat()
    assert result["remaining_minutes"] == 840


def test_grant_from_paused_profile_expires_to_paused(now):
    state, router, bound = fixture(now)
    router.tables["kids"][0]["paused"] = "true"
    temporary(state, router, now)
    result = project(state, router, bound, now)
    assert result["allows"] is True
    assert result["next_allows"] is False and result["remaining_minutes"] == 30


def test_timed_pause_expires_to_schedule_not_unconditional_access(now):
    now = now.replace(hour=23)
    state, router, bound = fixture(now)
    temporary(state, router, now, "timed_pause")
    result = project(state, router, bound, now)
    assert result["allows"] is False
    assert result["temporary_until"] == now.replace(minute=30).isoformat()
    assert result["next_change_at"] == (now + timedelta(days=1)).replace(hour=8).isoformat()
    assert result["next_allows"] is True and result["remaining_minutes"] is None


@pytest.mark.parametrize("phase", ["queued", "applying", "rolling_back", "review_required"])
def test_nonterminal_and_review_states_do_not_claim_access(now, phase):
    state, router, bound = fixture(now)
    p = temporary(state, router, now)
    p["status"] = phase
    assert project(state, router, bound, now)["reason"] == "changing"


def test_no_timer_verification_or_external_change(now):
    state, router, bound = fixture(now)
    p = temporary(state, router, now)
    p["progress"]["timer_verified"] = False
    assert project(state, router, bound, now)["mode"] == "unknown"
    p["progress"]["timer_verified"] = True
    router.tables["kids"][0]["rate-limit"] = "8M"
    assert project(state, router, bound, now)["mode"] == "unknown"


def test_early_router_restore_and_observation_before_effect(now):
    state, router, bound = fixture(now)
    p = temporary(state, router, now)
    p["updated_at"] = (now + timedelta(seconds=1)).isoformat()
    assert project(state, router, bound, now)["reason"] == "changing"
    observe(state, router, now + timedelta(seconds=2))
    router.tables["kids"][0].update(p["before"])
    result = project(state, router, bound, now + timedelta(seconds=2))
    assert result["mode"] == "schedule" and result["temporary_until"] is None


def test_old_backend_plans_cannot_change_summary(now):
    state, router, bound = fixture(now)
    p = temporary(state, router, now)
    p["backend"] = "retired-router"
    p["status"] = "review_required"
    assert project(state, router, bound, now)["reason"] == "fresh"
    assert project(state, router, bound, now)["temporary_until"] is None


@pytest.mark.asyncio
async def test_engine_projection_is_private_and_extrapolates_injected_time(engine, now):
    await prepare_engine(engine, now)
    before = engine.snapshot()
    view = engine.view("child", now=now)
    assert view["kid_control"]["profiles"][0]["status"]["remaining_minutes"] == 840
    assert "02:11:22" not in str(view)
    assert not engine.view("sibling", now=now)["kid_control"]["profiles"]
    assert (
        engine.view("child", now=now + timedelta(minutes=4))["kid_control"]["profiles"][0][
            "status"
        ]["mode"]
        == "unknown"
    )
    assert engine.snapshot() == before
