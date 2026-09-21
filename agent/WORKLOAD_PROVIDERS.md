# Workload provider API v1 (experimental)

A profile-scoped provider is registered with
`PluginContext.register_workload_provider(provider)`. Its `name` must be unique;
`api_version` must match `WORKLOAD_API_VERSION`. Unload restores displaced
registrations through the existing plugin lifecycle. Provider selection is keyed
by `hermes_home_key`, preserving multiplex profile isolation.

`workloads.mode` is `disabled` by default. `required` selects the explicitly named
`workloads.provider`; missing/incompatible registration, bad config and failed
execution calls raise `WorkloadUnavailable`. Required never falls back to Popen.
Providers advertise an immutable `supported_kinds` set. Currently wired kinds are
`terminal`, `terminal-pty`, `cron-script`. Delegation and agent cron remain explicitly
unsupported until an isolated agent control protocol exists.

`popen(kind, argv, config=..., **kwargs)` is an execution-owner operation, not an
advisory hook. It must reserve before spawn, return an appropriate Popen/PTY handle,
retain ownership after background/yield, and verify descendant cleanup before
release. Managed handles set `_hermes_managed = True` so termination goes through
the execution owner instead of PID-only upstream cleanup. Disabled paths retain
upstream process/scope handling. A metadata `submit(WorkloadSpec)` ticket alone is
never authorization for core to launch a workload.

No queue policy, cgroup backend or provider module name belongs in core. The
consumer implementation and its acceptance/operations records live separately in
LM3Labs/hermes/apps/hermes-worker-queue. This API does not provide agent approval,
steering, secret resolution or durable result transport and must not be described
as full agent enforcement.
