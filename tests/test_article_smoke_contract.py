"""Keep the actual-HA synthetic provider aligned with the real answer schema."""

from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from custom_components.family_assistant.assistant import plans


@pytest.mark.asyncio
async def test_ha_article_provider_uses_real_article_schema():
    path = Path(__file__).with_name("ha_article_smoke.py")
    spec = spec_from_file_location("synthetic_ha_article_contract", path)
    assert spec is not None and spec.loader is not None
    helper = module_from_spec(spec)
    spec.loader.exec_module(helper)
    cascade = helper._Cascade()
    checks = []

    async def scope():
        checks.append(True)

    result = await cascade.generate(
        plans.article_messages(
            "en", {"title": "Public article", "text": "Public evidence."}, datetime.now(UTC)
        ),
        plans.ARTICLE_SCHEMA,
        plans.validate_article_answer,
        scope_check=scope,
    )
    assert result == {"kind": "answer", "text": "Synthetic answer without a URL."}
    assert checks == [True]
    assert cascade.calls == 1
