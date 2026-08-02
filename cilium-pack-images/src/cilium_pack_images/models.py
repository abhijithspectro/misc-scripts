from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ImageRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    tag: str
    repository: str = ""
    source_path: str = ""


class PackTagPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["chart", "pack_version", "history", "pinned"] = "chart"
    value: str | None = None

    @model_validator(mode="after")
    def pinned_requires_value(self) -> PackTagPolicy:
        if self.source == "pinned" and not self.value:
            msg = "pack_tag.source=pinned requires pack_tag.value"
            raise ValueError(msg)
        return self


class MappingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_paths: list[str] = Field(min_length=1)
    operator_variant: str | None = None
    pack_tag: PackTagPolicy = Field(default_factory=PackTagPolicy)


class RegistryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str = (
        "us-docker.pkg.dev/palette-images/hardened-images/packs/cilium/{version}/{name}:{tag}"
    )


class ChartFetchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url_template: str = (
        "https://raw.githubusercontent.com/cilium/cilium/v{version}/install/kubernetes/cilium/values.yaml"
    )


class MappingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    normalize_tags: bool = True
    registry: RegistryConfig = Field(default_factory=RegistryConfig)
    chart: ChartFetchConfig = Field(default_factory=ChartFetchConfig)
    images: dict[str, MappingEntry]
    ignore_chart_paths: list[str] = Field(default_factory=list)


class HistoryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    last_pack_version: str = ""
    images: dict[str, str] = Field(default_factory=dict)


class CompareFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    message: str
    pack_name: str | None = None
    pack_tag: str | None = None
    chart_path: str | None = None
    chart_repository: str | None = None
    chart_tag: str | None = None


class CompareReport(BaseModel):
    pack_images: list[ImageRef]
    chart_images: list[ImageRef]
    findings: list[CompareFinding]

    @property
    def ok(self) -> bool:
        return not self.findings


class PreparedImage(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    tag: str
    tag_source: str
    chart_path: str | None = None
    chart_tag: str | None = None
    image: str


class PrepareReport(BaseModel):
    pack_version: str
    chart_source: str
    images: list[PreparedImage]
    new_chart_images: list[ImageRef]
    notes: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.new_chart_images
