"""Fetch Cilium pack image name/tag list via cilium-pack-images."""

from pathlib import Path

import cilium_pack_images
from cilium_pack_images.prepare import prepare_version

# Editable install: .../cilium-pack-images/src/cilium_pack_images/__init__.py
_PACK_IMAGES_ROOT = Path(cilium_pack_images.__file__).resolve().parents[2]
DEFAULT_MAPPING = _PACK_IMAGES_ROOT / "mapping.yaml"
DEFAULT_HISTORY = _PACK_IMAGES_ROOT / "history.yaml"
DEFAULT_CACHE = _PACK_IMAGES_ROOT / ".cache" / "charts"


def fetch_pack_images(
    pack_version: str,
    *,
    mapping_path: Path | None = None,
    history_path: Path | None = None,
    chart_values_path: Path | None = None,
    cache_dir: Path | None = None,
) -> list[tuple[str, str]]:
    """Return [(name, tag), ...] for a Cilium pack version.

    Does not update history.yaml.
    """
    report, _history = prepare_version(
        pack_version,
        mapping_path=mapping_path or DEFAULT_MAPPING,
        history_path=history_path or DEFAULT_HISTORY,
        chart_values_path=chart_values_path,
        cache_dir=cache_dir if chart_values_path is None else None,
    )
    if report.new_chart_images:
        names = ", ".join(img.source_path for img in report.new_chart_images)
        msg = f"upstream chart has unmapped images; update cilium-pack-images mapping first: {names}"
        raise ValueError(msg)
    return [(item.name, item.tag) for item in report.images]


def images_from_detailed_payload(payload: dict) -> list[tuple[str, str]]:
    images = payload.get("images")
    if not isinstance(images, list):
        msg = "detailed JSON must contain an images list"
        raise ValueError(msg)
    result: list[tuple[str, str]] = []
    for entry in images:
        if not isinstance(entry, dict) or "name" not in entry or "tag" not in entry:
            msg = "each images[] entry must include name and tag"
            raise ValueError(msg)
        result.append((str(entry["name"]), str(entry["tag"])))
    return result
