from pydantic import BaseModel, ConfigDict, Field


class SyncCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    dhi_repository: str
    pack_tags: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)


class DispatchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    dhi_repository: str
    dispatched: bool
    dry_run: bool
    detail: str = ""


class SyncPlan(BaseModel):
    pack_version: str
    repo: str
    workflow: str
    dry_run: bool
    delay_seconds: float = 30.0
    candidates: list[SyncCandidate]
    skipped_missing: list[str] = Field(default_factory=list)
    results: list[DispatchResult] = Field(default_factory=list)
