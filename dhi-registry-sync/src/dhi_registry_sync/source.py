"""Load or produce a DHI verify report used to select sync candidates."""

from __future__ import annotations

import json
from pathlib import Path

from dhi_catalog_check.models import VerifyReport
from dhi_catalog_check.pack_source import (
    DEFAULT_CACHE,
    DEFAULT_HISTORY,
    DEFAULT_MAPPING,
    fetch_pack_images,
)
from dhi_catalog_check.verify import verify_images


def load_verify_report(path: Path) -> VerifyReport:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = "verify report must be a JSON object"
        raise ValueError(msg)
    return VerifyReport.model_validate(data)


def run_dhi_lookup(
    pack_version: str,
    *,
    mapping_path: Path | None = None,
    history_path: Path | None = None,
    chart_values_path: Path | None = None,
    cache_dir: Path | None = None,
    docker_bin: str = "docker",
    max_workers: int = 8,
) -> VerifyReport:
    resolved_cache = None if chart_values_path is not None else (cache_dir or DEFAULT_CACHE)
    images = fetch_pack_images(
        pack_version,
        mapping_path=mapping_path or DEFAULT_MAPPING,
        history_path=history_path or DEFAULT_HISTORY,
        chart_values_path=chart_values_path,
        cache_dir=resolved_cache,
    )
    return verify_images(
        images,
        pack_version=pack_version,
        docker_bin=docker_bin,
        max_workers=max_workers,
    )
