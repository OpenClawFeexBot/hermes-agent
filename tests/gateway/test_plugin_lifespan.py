"""Gateway resources must be ready before startup and unwind on failed boot."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from gateway.run_startup import GatewayStartupMixin


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["adapter", "plugin", None])
async def test_discovered_lifespan_precedes_work_and_unwinds_failed_start(
    tmp_path, monkeypatch, failure
):
    from hermes_cli import plugins

    directory = tmp_path / "plugins" / "lifetest"
    directory.mkdir(parents=True)
    (directory / "plugin.yaml").write_text("name: lifetest\nversion: 1.0.0\n")
    (directory / "__init__.py").write_text("""
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifetime(*, gateway):
    if gateway.failure == "plugin":
        raise RuntimeError("plugin startup failed")
    gateway.events.append("ready")
    try:
        yield
    finally:
        gateway.events.append("closed")
def register(ctx):
    ctx.register_hook("gateway_lifespan", lifetime)
""")
    (tmp_path / "config.yaml").write_text("plugins:\n  enabled: [lifetest]\n")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    manager = plugins.PluginManager()
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)

    class Runner(GatewayStartupMixin):
        _running = False
        events = []

        async def _start_impl(self):
            assert self.events == ["ready"]
            self.events.append("work")
            if self.failure == "adapter":
                raise RuntimeError("adapter startup failed")
            self._running = True
            return True

        @staticmethod
        async def _start_flush_runtime_status():
            pass

    runner = Runner()
    runner.failure = failure
    try:
        if failure:
            with pytest.raises(RuntimeError, match=f"{failure} startup failed"):
                await runner.start()
            assert runner.events == (
                [] if failure == "plugin" else ["ready", "work", "closed"]
            )
        else:
            from gateway.run import GatewayRunner
            from gateway.run_shutdown import GatewayShutdownMixin

            await runner.start()

            async def phase(*args):
                assert runner.events == ["ready", "work"]

            for name in (
                "_stop_begin_teardown",
                "_stop_drain_active_work",
                "_stop_finalize_agents_and_adapters",
                "_stop_release_runtime_state",
            ):
                monkeypatch.setattr(GatewayRunner, name, phase)

            async def persist(*args):
                assert runner.events == ["ready", "work", "closed"]

            monkeypatch.setattr(GatewayRunner, "_stop_persist_exit_state", persist)
            monkeypatch.setattr(
                GatewayRunner, "_stop_quiesce_and_close_session_dbs", lambda *a: None
            )
            runner._restart_drain_timeout = 5
            await GatewayShutdownMixin._stop_impl(runner)
            assert runner.events == ["ready", "work", "closed"]
    finally:
        manager.unload()


@pytest.mark.asyncio
async def test_stop_during_resource_entry_waits_for_cleanup(monkeypatch):
    from gateway.plugin_lifespan import start_plugin_lifespans, stop_plugin_lifespans
    from hermes_cli import plugins

    entered, cleaned = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def resource(*, gateway):
        try:
            entered.set()
            await asyncio.Event().wait()
            yield
        finally:
            cleaned.set()

    manager = plugins.PluginManager()
    manager._discovered = True
    manager._hooks["gateway_lifespan"] = [resource]
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: manager)
    runner = SimpleNamespace()
    start = asyncio.create_task(start_plugin_lifespans(runner))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        await stop_plugin_lifespans(runner)
        assert cleaned.is_set(), "stop returned while resource entry still owned work"
        with pytest.raises(asyncio.CancelledError):
            await start
    finally:
        start.cancel()
        await asyncio.gather(start, return_exceptions=True)
