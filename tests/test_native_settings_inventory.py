"""Keep the durable inventory complete as native routes and controls evolve."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components/family_assistant"


def test_every_native_step_is_named_in_inventory():
    document = (ROOT / "docs/native-settings-audit.md").read_text(encoding="utf-8")
    steps = {
        node.name.removeprefix("async_step_")
        for file in ("config_flow.py", "onboarding_options.py")
        for node in ast.walk(ast.parse((PACKAGE / file).read_text(encoding="utf-8")))
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("async_step_")
    }
    missing = sorted(step for step in steps if f"| `{step}` |" not in document)
    assert not missing, missing


def test_new_native_controls_are_localized_in_all_catalogs():
    expected = {
        "telegram": {"clear_token"},
        "mikrotik": {"clear_password"},
        "alarm_device": {"member"},
        "presence_sources": {"member"},
        "presence_source_settings": {"enabled", "entity_id", "presence_max_age_seconds"},
        "alarm_device_settings": {
            "entity_id",
            "volume",
            "enabled",
            "confirmed",
            "duration_entity_id",
            "duration_seconds",
            "volume_entity_id",
            "select_volume",
            "clear_duration",
            "clear_volume",
        },
    }
    for file in (
        "strings.json",
        "translations/en.json",
        "translations/ru.json",
        "translations/uk.json",
    ):
        steps = json.loads((PACKAGE / file).read_text(encoding="utf-8"))["options"]["step"]
        for step, fields in expected.items():
            assert fields <= steps[step]["data"].keys(), (file, step)
            assert all(steps[step]["data"][key].strip() for key in fields)
        assert set(steps["alarm_device"]["data"]) == {"member"}
        assert set(steps["presence_sources"]["data"]) == {"member"}
        assert "{member}" in steps["presence_source_settings"]["description"]
