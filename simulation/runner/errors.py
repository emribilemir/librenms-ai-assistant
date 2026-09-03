"""Stable public result and error records for the restricted runner."""

from dataclasses import dataclass


PublicScalar = str | int | bool | None


class RunnerError(Exception):
    def __init__(self, code: str, *, retryable: bool = False, stage: str | None = None):
        self.code = code
        self.retryable = retryable
        self.stage = stage
        super().__init__(code)


@dataclass(frozen=True)
class RunnerEvent:
    event: str
    stage: str
    details: tuple[tuple[str, PublicScalar], ...] = ()


@dataclass(frozen=True)
class RunnerResult:
    success: bool
    code: str
    retryable: bool
    phase: str
    scenario_id: str | None
    details: tuple[tuple[str, PublicScalar], ...] = ()
