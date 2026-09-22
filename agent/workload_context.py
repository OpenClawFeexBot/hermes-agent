"""Authenticated worker bootstrap context, never model/config supplied identity.

One isolated process owns one root agent. Its tool threads share this immutable
lease; ordinary gateway processes never install it. The provider independently
verifies the submitting PID's actual scope membership.
"""
from agent.workload_provider import WorkloadLease

_worker_context = None


def install_worker_context(lease):
    global _worker_context
    validated = WorkloadLease(**lease)
    if _worker_context is not None:
        raise RuntimeError("worker workload context already installed")
    _worker_context = validated


def worker_lease():
    return _worker_context.to_dict() if _worker_context is not None else None
