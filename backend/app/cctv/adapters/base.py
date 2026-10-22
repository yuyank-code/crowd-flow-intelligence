from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capabilities:
    """Protocol-level facts. 'preview' is decided by the manager (needs a media gateway)."""
    snapshot: bool = False
    ptz: bool = False
    discovery: bool = False
    formats: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TestResult:
    __test__ = False  # not a pytest class
    status: str            # online | offline | auth_required | auth_failed | agent_offline | error
    code: str | None = None
    detail: str = ""


class CameraAdapter:
    source_type = ""
    capabilities = Capabilities()

    async def test(self, endpoint: str | None, creds: tuple[str, str] | None, timeout: float) -> TestResult:
        raise NotImplementedError
