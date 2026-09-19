"""Tests for the consumer-facing thin-caller reusable workflow."""
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).parent.parent
REUSABLE = REPO_ROOT / ".github" / "workflows" / "reusable-thin-caller-gate.yml"


def test_reusable_declares_workflow_call():
    workflow = yaml.safe_load(REUSABLE.read_text(encoding="utf-8"))
    # YAML 1.1 parses the bare key `on:` as boolean True under PyYAML.
    on_key = "on" if "on" in workflow else True
    assert "workflow_call" in workflow[on_key]


def test_reusable_runs_canonical_script():
    body = REUSABLE.read_text(encoding="utf-8")
    assert "projectbluefin/actions" in body
    assert "validate_thin_caller.py" in body
    assert "--max-lines 50" in body
