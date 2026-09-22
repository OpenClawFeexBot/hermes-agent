"""Actual delegation/cron construction carries estimates across worker threads."""
import json
from concurrent.futures import ThreadPoolExecutor

from tests.agent.test_isolated_agent import local_model
from tests.agent.test_isolated_queue_integration import queue_home


def test_batch_delegation_keeps_individual_estimates(queue_home, local_model):
    from run_agent import AIAgent
    from tools.delegate_tool import delegate_task

    home, state, client, provider, backend = queue_home
    url, requests = local_model
    parent = AIAgent(model="fixture", provider="custom", base_url=url, api_key="fixture-key",
                     enabled_toolsets=[], skip_memory=True, skip_context_files=True,
                     quiet_mode=True)
    try:
        result = json.loads(delegate_task(tasks=[
            {"goal": "Return the first brief fixture response", "estimated_peak_memory_mb": 768,
             "estimated_retained_memory_mb": 400},
            {"goal": "Return the second brief fixture response", "estimated_peak_memory_mb": 800,
             "estimated_retained_memory_mb": 432},
        ], parent_agent=parent))
        assert not result.get("error"), result
        rows = [r for r in client.call("status")["jobs"] if r["kind"] == "delegation"]
        assert sorted(r["peak"] for r in rows) == [768 * 1024**2, 800 * 1024**2], rows
        assert sorted(r["retained"] for r in rows) == [400 * 1024**2, 432 * 1024**2], rows
        assert all(r["estimate_source"] == "job" and r["parent_ticket"] is None for r in rows)
        assert client.call("status")["reserved"] == 0
    finally:
        parent.close()


def test_live_single_goal_dispatch_estimate_reaches_queue(queue_home, local_model):
    from run_agent import AIAgent

    home, state, client, provider, backend = queue_home
    url, requests = local_model
    parent = AIAgent(model="fixture", provider="custom", base_url=url, api_key="fixture-key",
                     enabled_toolsets=[], skip_memory=True, skip_context_files=True,
                     quiet_mode=True)
    try:
        result = json.loads(parent._dispatch_delegate_task({
            "goal": "Return a short fixture response", "estimated_peak_memory_mb": 768,
            "estimated_retained_memory_mb": 400,
            "parent_lease": {"ticket": "forged", "generation": "forged"},
        }))
        assert not result.get("error"), result
        rows = [r for r in client.call("status")["jobs"] if r["kind"] == "delegation"]
        assert len(rows) == 1 and rows[0]["peak"] == 768 * 1024**2, rows
        assert rows[0]["retained"] == 400 * 1024**2
        assert rows[0]["estimate_source"] == "job" and rows[0]["parent_ticket"] is None
        assert client.call("status")["reserved"] == 0
    finally:
        parent.close()


def test_cron_agent_estimate_survives_watchdog_thread(queue_home, local_model):
    from cron.jobs import create_job, get_job, use_cron_store
    from cron.scheduler import run_job

    home, state, client, provider, backend = queue_home
    url, requests = local_model
    with use_cron_store(home):
        job = create_job("Return a short fixture response", "every 2h", model="fixture",
                         provider="custom", base_url=url, estimated_peak_memory_mb=768,
                         estimated_retained_memory_mb=400)
        assert client.call("status")["jobs"] == []
        result = run_job(get_job(job["id"]))
        assert result[0], result
        rows = [r for r in client.call("status")["jobs"] if r["kind"] == "cron-agent"]
        assert len(rows) == 1 and rows[0]["peak"] == 768 * 1024**2, rows
        assert rows[0]["retained"] == 400 * 1024**2
        assert rows[0]["estimate_source"] == "job"
        assert client.call("status")["reserved"] == 0
