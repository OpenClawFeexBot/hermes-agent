"""Wire-level workload metadata; policy and execution belong to providers."""

from dataclasses import asdict, dataclass
from abc import ABC, abstractmethod
import re

WORKLOAD_API_VERSION = 1


class WorkloadUnavailable(RuntimeError):
    """Required protection cannot authorize this execution."""


class WorkloadProvider(ABC):
    """Versioned execution-owner contract; a ticket is never authorization.

    Providers advertise supported kinds explicitly. ``popen`` owns admission,
    spawn, termination and completion; unsupported modes must fail closed.
    This API does not authorize serializing agents, callbacks or live clients.
    """

    api_version = WORKLOAD_API_VERSION
    name: str

    supported_kinds = frozenset()

    def popen(self, kind, args, *, config, **kwargs):
        """Own launch and lifetime; return a Popen-compatible handle, never a lease."""
        raise WorkloadUnavailable(f"unsupported workload execution: {kind}")

    @abstractmethod
    def submit(self, spec: "WorkloadSpec") -> dict:
        """Return a queued ticket or raise; never run a caller closure."""


def positive_bytes(value):
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError("memory must be positive integer bytes below 2**63")
    return value


@dataclass(frozen=True)
class WorkloadSpec:
    request_id: str
    kind: str
    owner: str
    domain: str
    peak_memory_bytes: int
    backend: str = "local"

    def __post_init__(self):
        positive_bytes(self.peak_memory_bytes)
        for value in (
            self.request_id,
            self.kind,
            self.owner,
            self.domain,
            self.backend,
        ):
            if not isinstance(value, str) or not re.fullmatch(
                r"[A-Za-z0-9_.:-]{1,128}", value
            ):
                raise ValueError("workload identifiers must be bounded opaque tokens")

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        try:
            return cls(**value)
        except TypeError as exc:
            raise ValueError("invalid workload metadata") from exc
