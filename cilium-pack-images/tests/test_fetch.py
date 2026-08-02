from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from cilium_pack_images.fetch import fetch_chart_values
from cilium_pack_images.models import MappingConfig, MappingEntry


def test_fetch_chart_values_caches(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    mapping = MappingConfig(
        images={"cilium": MappingEntry(chart_paths=["image"])},
    )
    url = mapping.chart.url_template.format(version="1.20.0")
    httpx_mock.add_response(url=url, text="image:\n  repository: quay.io/cilium/cilium\n  tag: v1.20.0\n")

    data, source = fetch_chart_values(mapping, "1.20.0", cache_dir=tmp_path)
    assert data["image"]["tag"] == "v1.20.0"
    assert source == url
    cached = tmp_path / "v1.20.0" / "values.yaml"
    assert cached.exists()

    # Second call should hit cache (no additional HTTP mock needed).
    data2, source2 = fetch_chart_values(mapping, "1.20.0", cache_dir=tmp_path)
    assert data2["image"]["tag"] == "v1.20.0"
    assert source2 == str(cached)


def test_fetch_chart_values_404(httpx_mock: HTTPXMock) -> None:
    mapping = MappingConfig(
        images={"cilium": MappingEntry(chart_paths=["image"])},
    )
    url = mapping.chart.url_template.format(version="0.0.0")
    httpx_mock.add_response(url=url, status_code=404)

    with pytest.raises(FileNotFoundError, match="upstream chart not found"):
        fetch_chart_values(mapping, "0.0.0")
