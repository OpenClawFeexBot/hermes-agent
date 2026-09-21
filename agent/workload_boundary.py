"""Generic execution-owner selection; no scheduler policy or inline fallback."""

import subprocess
from agent.workload_provider import WorkloadUnavailable
from agent.workload_registry import select_provider


def workload_config():
    from hermes_cli.config_effective import load_user_config_effective

    try:
        config = load_user_config_effective(fail_closed=True).get("workloads", {})
    except Exception as exc:
        raise WorkloadUnavailable("workload configuration unavailable") from exc
    if not isinstance(config, dict):
        raise WorkloadUnavailable("invalid workload configuration")
    return config


def require_unmanaged_allowed(kind):
    if workload_config().get("mode", "disabled") != "disabled":
        raise WorkloadUnavailable(
            f"Required workload protection: unsupported execution adapter: {kind}"
        )


def execution_provider(kind):
    provider = select_provider(workload_config())
    if provider is not None and kind not in provider.supported_kinds:
        raise WorkloadUnavailable(
            f"Required workload protection: unsupported execution adapter: {kind}"
        )
    return provider


def popen(kind, args, **kwargs):
    config = workload_config()
    provider = select_provider(config)
    if provider is None:
        return subprocess.Popen(args, **kwargs)
    if kind not in provider.supported_kinds:
        raise WorkloadUnavailable(f"unsupported workload execution: {kind}")
    try:
        return provider.popen(kind, args, config=config, **kwargs)
    except Exception as exc:
        raise WorkloadUnavailable("workload execution-owner launch failed") from exc
