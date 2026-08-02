from pydantic import BaseModel, ConfigDict, Field


class ImageCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    tag: str
    ref: str
    present: bool
    reason: str | None = None


class VerifyReport(BaseModel):
    pack_version: str
    registry: str
    all_present: bool
    present: list[ImageCheck] = Field(default_factory=list)
    missing: list[ImageCheck] = Field(default_factory=list)
    checked: int = 0
