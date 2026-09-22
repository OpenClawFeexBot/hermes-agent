"""Live agent interception must retain legacy single-goal memory metadata."""
import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("batched", [False, True])
def test_live_dispatch_preserves_estimates(monkeypatch, tmp_path, batched):
    from run_agent import AIAgent
    from tools import delegate_tool

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(delegate_tool, "_resolve_delegation_credentials", lambda *a: {})
    monkeypatch.setattr(delegate_tool, "_announce_batch", lambda *a: None)
    captured = []

    def stop_before_construction(tasks, *args, **kwargs):
        captured.extend(tasks)
        return [], "construction boundary reached"

    monkeypatch.setattr(delegate_tool, "_build_children", stop_before_construction)
    task = {"goal": "Check memory plumbing", "estimated_peak_memory_mb": 768,
            "estimated_retained_memory_mb": 400}
    args = {"tasks": [task]} if batched else task
    result = json.loads(AIAgent._dispatch_delegate_task(SimpleNamespace(_delegate_depth=0), args))
    assert result["error"] == "construction boundary reached"
    assert captured[0]["estimated_peak_memory_mb"] == 768
    assert captured[0]["estimated_retained_memory_mb"] == 400


def test_live_dispatch_rejects_invalid_estimate_before_construction(monkeypatch, tmp_path):
    from run_agent import AIAgent
    from tools import delegate_tool

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(delegate_tool, "_resolve_delegation_credentials", lambda *a: {})
    monkeypatch.setattr(delegate_tool, "_announce_batch", lambda *a: None)
    monkeypatch.setattr(delegate_tool, "_build_children", lambda *a, **kw: pytest.fail("child constructed"))
    result = json.loads(AIAgent._dispatch_delegate_task(SimpleNamespace(_delegate_depth=0), {
        "goal": "Must not start", "estimated_peak_memory_mb": True,
    }))
    assert "positive integer MiB" in result["error"]
