import json
from types import SimpleNamespace
import pytest


@pytest.fixture
def required(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    (tmp_path / "config.yaml").write_text(
        "workloads:\n  mode: required\n  provider: absent\n"
    )
    return tmp_path


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"background": True}, {"background": True, "pty": True}, {"timeout": 700}],
)
def test_terminal_required_refuses_before_side_effect(required, kwargs):
    from tools.terminal_tool import terminal_tool

    target = required / "spawned"
    result = json.loads(terminal_tool(f"touch {target}", **kwargs))
    assert "workload" in result.get("error", "").lower()
    assert not target.exists()


@pytest.mark.parametrize(
    "kwargs", [{}, {"background": True}, {"tasks": [{"goal": "a"}, {"goal": "b"}]}]
)
def test_delegation_required_refuses_before_agent_construction(required, kwargs):
    from tools.delegate_tool import delegate_task

    result = json.loads(
        delegate_task(goal="test", parent_agent=SimpleNamespace(), **kwargs)
    )
    assert "workload" in result.get("error", "").lower()


@pytest.mark.parametrize("path", ["local", "background", "remote", "script", "child"])
def test_direct_callers_cannot_bypass_required_boundary(required, path):
    from agent.workload_provider import WorkloadUnavailable

    with pytest.raises(WorkloadUnavailable):
        if path == "local":
            from tools.environments.local import LocalEnvironment

            LocalEnvironment._run_bash(SimpleNamespace(), "true")
        elif path == "background":
            from tools.process_registry import ProcessRegistry

            ProcessRegistry.spawn_local(SimpleNamespace(), "true")
        elif path == "remote":
            from tools.process_registry import ProcessRegistry

            ProcessRegistry.spawn_via_env(SimpleNamespace(), SimpleNamespace(), "true")
        elif path == "script":
            from cron.scheduler_script import _run_job_script

            _run_job_script("missing")
        else:
            from tools.delegate_tool import _build_child_agent

            _build_child_agent(0, "goal", None, None, None, 1, 1, SimpleNamespace())


def test_unreadable_policy_cannot_become_disabled(required):
    from agent.workload_boundary import require_unmanaged_allowed
    from agent.workload_provider import WorkloadUnavailable

    (required / "config.yaml").write_text("workloads: [invalid yaml")
    with pytest.raises(WorkloadUnavailable):
        require_unmanaged_allowed("terminal")


def test_cron_required_refuses_before_script_or_agent(required):
    from cron.scheduler import run_job

    result = run_job({
        "id": "test",
        "name": "test",
        "no_agent": True,
        "script": "missing",
    })
    assert result[0] is False
    assert "workload" in str(result).lower()
