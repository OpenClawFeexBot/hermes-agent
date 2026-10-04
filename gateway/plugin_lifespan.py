"""Required plugin resources owned by one gateway runner, not observer hooks."""

import asyncio
from contextlib import AsyncExitStack


async def start_plugin_lifespans(gateway):
    from hermes_cli.plugins import _ensure_plugins_discovered

    if (
        getattr(gateway, "_plugin_lifespan_stack", None) is not None
        or getattr(gateway, "_plugin_lifespan_start_task", None) is not None
    ):
        raise RuntimeError("gateway plugin lifespans already started")
    manager = _ensure_plugins_discovered()
    stack = AsyncExitStack()
    gateway._plugin_lifespan_start_task = asyncio.current_task()
    try:
        for factory in manager.iter_hook_callbacks("gateway_lifespan"):
            await stack.enter_async_context(factory(gateway=gateway))
    except BaseException:
        await stack.aclose()
        raise
    finally:
        gateway._plugin_lifespan_start_task = None
    gateway._plugin_lifespan_stack = stack


async def stop_plugin_lifespans(gateway):
    starting = getattr(gateway, "_plugin_lifespan_start_task", None)
    if starting is not None and starting is not asyncio.current_task():
        starting.cancel()
        await asyncio.gather(starting, return_exceptions=True)
    stack = getattr(gateway, "_plugin_lifespan_stack", None)
    if stack is not None:
        gateway._plugin_lifespan_stack = None
        await stack.aclose()
