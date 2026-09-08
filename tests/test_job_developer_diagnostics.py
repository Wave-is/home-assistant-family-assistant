"""Opt-in technical counts are atomic with actual job completion and delivery."""

from copy import deepcopy

import pytest
from test_job_completion_authority import Clock, _configured, _model_results

from custom_components.family_assistant.domain.developer_diagnostics import (
    build_report,
    capture_generation,
)


async def consent(engine, now, enabled, operation):
    from custom_components.family_assistant.domain.developer_diagnostics import configuration

    return await engine.execute(
        "owner",
        "settings.developer_policy",
        {"enabled": enabled, "expected_generation": configuration(engine.snapshot())["generation"]},
        operation,
        now,
    )


@pytest.mark.asyncio
async def test_completion_count_and_outbox_commit_together_once(engine, store, now):
    await consent(engine, now, True, "optin")
    jobs, job = await _configured(engine, now, Clock(now))
    assert job["diagnostic_generation"] == capture_generation(engine.snapshot())
    before = engine.snapshot()
    store.fail = True
    with pytest.raises(OSError):
        await jobs.finish(job, "PRIVATE_REPLY", now, diagnostic_code="provider_timeout")
    assert engine.snapshot() == before
    store.fail = False
    await jobs.finish(job, "PRIVATE_REPLY", now, diagnostic_code="provider_timeout")
    committed = engine.snapshot()
    await jobs.finish(job, "Duplicate", now, diagnostic_code="provider_timeout")
    assert engine.snapshot() == committed
    assert len(_model_results(committed)) == 1
    report = build_report(committed, version="0.1.0-alpha.28")
    assert report["cases"] == [
        {
            "stage": "assistant_job",
            "code": "provider_timeout",
            "has_quote": False,
            "has_refs": False,
            "count": 1,
        }
    ]
    assert "PRIVATE_REPLY" not in str(report)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["default", "optout", "aba", "success", "cancel", "tampered", "bad_store"]
)
async def test_no_collection_outside_exact_current_consent(engine, now, case):
    if case != "default":
        await consent(engine, now, True, "optin")
    jobs, job = await _configured(engine, now, Clock(now))
    if case in {"optout", "aba"}:
        await consent(engine, now, False, "optout")
        if case == "aba":
            await consent(engine, now, True, "reenable")
    if case == "tampered":
        job = {**job, "diagnostic_generation": job["diagnostic_generation"] + 1}
    if case == "bad_store":

        def corrupt(ctx):
            ctx.state["memory"]["developer_diagnostics"]["cases"] = [{"code": []}]

        await engine.system_update("synthetic-corruption", now, corrupt)
    prior = deepcopy(engine.snapshot()["memory"].get("developer_diagnostics"))
    await jobs.finish(
        job,
        "Normal delivery remains available",
        now,
        cancelled=case == "cancel",
        diagnostic_code=None if case == "success" else "provider_timeout",
    )
    assert engine.snapshot()["memory"].get("developer_diagnostics") == prior
    assert len(_model_results(engine.snapshot())) == (0 if case in {"cancel", "tampered"} else 1)
