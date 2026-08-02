from pathlib import Path

import httpx
import yaml

from cilium_pack_images.models import MappingConfig


def chart_url(mapping: MappingConfig, version: str) -> str:
    return mapping.chart.url_template.format(version=version)


def fetch_chart_values(
    mapping: MappingConfig,
    version: str,
    *,
    cache_dir: Path | None = None,
    timeout: float = 60.0,
) -> tuple[dict, str]:
    """Fetch upstream chart values.yaml for a Cilium version.

    Returns (parsed_values, source_description).
    """
    url = chart_url(mapping, version)
    if cache_dir is not None:
        cached = cache_dir / f"v{version}" / "values.yaml"
        if cached.exists():
            data = yaml.safe_load(cached.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                msg = f"cached chart values are not a mapping: {cached}"
                raise ValueError(msg)
            return data, str(cached)

    response = httpx.get(url, follow_redirects=True, timeout=timeout)
    if response.status_code == 404:
        msg = f"upstream chart not found for version {version}: {url}"
        raise FileNotFoundError(msg)
    response.raise_for_status()

    data = yaml.safe_load(response.text)
    if not isinstance(data, dict):
        msg = f"upstream chart values are not a mapping: {url}"
        raise ValueError(msg)

    if cache_dir is not None:
        cached = cache_dir / f"v{version}" / "values.yaml"
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(response.text, encoding="utf-8")

    return data, url


def load_chart_values_file(path: Path) -> tuple[dict, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"chart values are not a mapping: {path}"
        raise ValueError(msg)
    return data, str(path)
