from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from cilium_pack_images.models import HistoryConfig, ImageRef, MappingConfig


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def dump_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, default_flow_style=False)


def load_mapping(path: Path) -> MappingConfig:
    data = load_yaml(path)
    if not isinstance(data, dict):
        msg = f"mapping file must be a mapping document: {path}"
        raise ValueError(msg)
    return MappingConfig.model_validate(data)


def load_history(path: Path) -> HistoryConfig:
    if not path.exists():
        return HistoryConfig()
    data = load_yaml(path)
    if data is None:
        return HistoryConfig()
    if not isinstance(data, dict):
        msg = f"history file must be a mapping document: {path}"
        raise ValueError(msg)
    return HistoryConfig.model_validate(data)


def history_from_pack_images(pack_images: list[ImageRef], *, pack_version: str) -> HistoryConfig:
    return HistoryConfig(
        last_pack_version=pack_version,
        images={image.name: image.tag for image in pack_images},
    )


def parse_image_ref(image: str, *, source_path: str = "pack.content.images") -> ImageRef:
    """Parse `registry/path/name:tag` into name + tag."""
    last_segment = image.rsplit("/", 1)[-1]
    if "@" in last_segment:
        msg = f"digest refs are not supported in pack metadata: {image}"
        raise ValueError(msg)
    if ":" not in last_segment:
        msg = f"image missing tag: {image}"
        raise ValueError(msg)

    repository, tag = image.rsplit(":", 1)
    name = repository.rsplit("/", 1)[-1]
    return ImageRef(name=name, tag=tag, repository=repository, source_path=source_path)


def extract_pack_images(pack_values: dict[str, Any]) -> list[ImageRef]:
    try:
        entries = pack_values["pack"]["content"]["images"]
    except (KeyError, TypeError) as exc:
        msg = "pack values missing pack.content.images"
        raise ValueError(msg) from exc

    if not isinstance(entries, list):
        msg = "pack.content.images must be a list"
        raise ValueError(msg)

    images: list[ImageRef] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or "image" not in entry:
            msg = f"pack.content.images[{index}] must be an object with an image key"
            raise ValueError(msg)
        images.append(parse_image_ref(str(entry["image"]), source_path=f"pack.content.images[{index}]"))
    return images


def _looks_like_image_block(value: dict[str, Any]) -> bool:
    return "repository" in value and "tag" in value


def extract_chart_images(chart_values: dict[str, Any]) -> list[ImageRef]:
    """Walk chart values and collect objects that look like Helm image blocks."""
    found: list[ImageRef] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if _looks_like_image_block(node):
                repository = str(node.get("repository") or "")
                tag = str(node.get("tag") or "")
                found.append(
                    ImageRef(
                        name=_repo_name(repository),
                        tag=tag,
                        repository=repository,
                        source_path=path,
                    )
                )
            for key, child in node.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]")

    walk(chart_values, "")
    return found


def _repo_name(repository: str) -> str:
    if not repository:
        return ""
    # Handle both registry/path and bare names.
    parsed = urlparse(repository if "://" in repository else f"//{repository}")
    path = parsed.path or repository
    return path.rsplit("/", 1)[-1]


def get_by_path(data: dict[str, Any], dotted: str) -> Any:
    current: Any = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            msg = f"path not found: {dotted}"
            raise KeyError(msg)
        current = current[part]
    return current
