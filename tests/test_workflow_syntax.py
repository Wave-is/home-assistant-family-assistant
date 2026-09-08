"""Local YAML syntax guard; this does not replace GitHub Actions validation."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda path: path.name)
def test_workflow_yaml_and_step_commands_are_well_formed(path):
    # YAML 1.1 SafeLoader interprets unquoted `on` as True. This checks syntax,
    # not GitHub's expression/type semantics, and never constructs Python objects.
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict) and ("on" in value or True in value)
    assert isinstance(value.get("jobs"), dict) and value["jobs"]
    for job in value["jobs"].values():
        assert isinstance(job, dict)
        for step in job.get("steps", []):
            assert isinstance(step, dict)
            if "run" in step:
                assert isinstance(step["run"], str) and step["run"].strip()


def test_pdf_bootstrap_is_used_in_each_offline_ha_lane():
    value = yaml.safe_load(
        (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8"),
    )
    for name in ("home-assistant", "encrypted-restore", "application-upgrade", "hacs-installer"):
        commands = [step["run"] for step in value["jobs"][name]["steps"] if "run" in step]
        docker = next(command for command in commands if "docker run" in command)
        assert "--network none" in docker and "--cap-drop ALL" in docker
        assert "ha_dependency_smoke.py" in docker and "pypdf-6.17.0-py3-none-any.whl" in docker
