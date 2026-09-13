"""Check declaration coverage, optionally against a LOCAL legacy source tree.

This is not a migration or behavior test. It parses only the two known Python
setup modules without importing/executing them. It never reads YAML, Store,
credentials, logs, or arbitrary default values. Output is fixed codes/counts.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"replaced", "review_required", "missing"}
SOURCES = {"family_assistant", "family_court"}


def declared_keys(source: str) -> set[str]:
    """Read CONF_* string declarations only; do not evaluate any source code."""
    result = set()
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        name = getattr(node.targets[0], "id", "")
        if name.startswith("CONF_") and isinstance(node.value, ast.Constant):
            value = node.value.value
            if not isinstance(value, str) or not value.isidentifier():
                raise ValueError("unsupported_configuration_declaration")
            result.add(value)
    return result


def validate(inventory: dict, sources: dict[str, str] | None = None) -> dict:
    if inventory.get("schema") != 1 or set(inventory.get("sources", {})) != SOURCES:
        raise ValueError("invalid_inventory")
    summary = dict.fromkeys(sorted(STATUSES), 0)
    for name, groups in inventory["sources"].items():
        if set(groups) != STATUSES:
            raise ValueError("invalid_inventory_status")
        keys = set()
        for status, values in groups.items():
            if not isinstance(values, list) or any(
                not isinstance(v, str) or not v.isidentifier() for v in values
            ):
                raise ValueError("invalid_inventory_key")
            if len(set(values)) != len(values) or keys.intersection(values):
                raise ValueError("duplicate_inventory_key")
            keys.update(values)
            summary[status] += len(values)
        if sources is not None and declared_keys(sources[name]) != keys:
            raise ValueError("legacy_configuration_coverage_changed")
    return {
        "status": "declarations_accounted_for",
        "source_verified": sources is not None,
        **summary,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", type=Path)
    args = parser.parse_args()
    try:
        inventory = json.loads(
            (ROOT / "docs/legacy-settings-inventory.json").read_text(encoding="utf-8")
        )
        sources = None
        if args.legacy_root:
            root = args.legacy_root.resolve(strict=True)
            sources = {}
            for module in sorted(SOURCES):
                candidate = root / "custom_components" / module / "__init__.py"
                resolved = candidate.resolve(strict=True)
                if not resolved.is_relative_to(root) or resolved.stat().st_size > 1024 * 1024:
                    raise ValueError("unsafe_source")
                sources[module] = resolved.read_text(encoding="utf-8-sig")
        print(json.dumps(validate(inventory, sources), sort_keys=True))
    except (OSError, ValueError, SyntaxError, KeyError):
        print(json.dumps({"status": "coverage_check_failed"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
