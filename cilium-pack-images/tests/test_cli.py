from pathlib import Path

import yaml
from click.testing import CliRunner

from cilium_pack_images.cli import main


def test_compare_cli_ok(tmp_path: Path) -> None:
    pack = tmp_path / "pack.yaml"
    chart = tmp_path / "chart.yaml"
    mapping = tmp_path / "mapping.yaml"
    pack.write_text(
        yaml.safe_dump(
            {
                "pack": {
                    "content": {
                        "images": [{"image": "reg/cilium:1.0.0"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    chart.write_text(
        yaml.safe_dump({"image": {"repository": "quay.io/cilium/cilium", "tag": "v1.0.0"}}),
        encoding="utf-8",
    )
    mapping.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "normalize_tags": True,
                "images": {"cilium": {"chart_paths": ["image"]}},
                "ignore_chart_paths": [],
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "compare",
            "--pack-values",
            str(pack),
            "--chart-values",
            str(chart),
            "--mapping",
            str(mapping),
        ],
    )
    assert result.exit_code == 0
    assert "OK" in result.output


def test_compare_cli_json_drift(tmp_path: Path) -> None:
    pack = tmp_path / "pack.yaml"
    chart = tmp_path / "chart.yaml"
    mapping = tmp_path / "mapping.yaml"
    pack.write_text(
        yaml.safe_dump({"pack": {"content": {"images": [{"image": "reg/cilium:1.0.0"}]}}}),
        encoding="utf-8",
    )
    chart.write_text(
        yaml.safe_dump(
            {
                "image": {"repository": "quay.io/cilium/cilium", "tag": "v1.0.0"},
                "extra": {"image": {"repository": "quay.io/cilium/extra", "tag": "1"}},
            }
        ),
        encoding="utf-8",
    )
    mapping.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "images": {"cilium": {"chart_paths": ["image"]}},
                "ignore_chart_paths": [],
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "compare",
            "--pack-values",
            str(pack),
            "--chart-values",
            str(chart),
            "--mapping",
            str(mapping),
            "--json",
        ],
    )
    assert result.exit_code == 1
    assert "unmapped_chart_image" in result.output
