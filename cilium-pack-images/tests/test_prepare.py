import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from cilium_pack_images.cli import main
from cilium_pack_images.models import HistoryConfig, MappingConfig, MappingEntry, PackTagPolicy
from cilium_pack_images.prepare import (
    prepare,
    report_to_detailed_payload,
    report_to_names_payload,
    report_to_pack_images_yaml,
)


def _mapping() -> MappingConfig:
    return MappingConfig(
        images={
            "cilium": MappingEntry(
                chart_paths=["image"],
                pack_tag=PackTagPolicy(source="chart"),
            ),
            "cilium-envoy": MappingEntry(
                chart_paths=["envoy.image"],
                pack_tag=PackTagPolicy(source="pack_version"),
            ),
            "spire-agent": MappingEntry(
                chart_paths=["spire.agent.image"],
                pack_tag=PackTagPolicy(source="history"),
            ),
        }
    )


def test_prepare_resolves_tags_and_detects_new() -> None:
    chart_values = {
        "image": {"repository": "quay.io/cilium/cilium", "tag": "v1.20.0"},
        "envoy": {"image": {"repository": "quay.io/cilium/cilium-envoy", "tag": "v1.99.0"}},
        "spire": {"agent": {"image": {"repository": "ghcr.io/spiffe/spire-agent", "tag": "1.9.6"}}},
        "brandNew": {"image": {"repository": "quay.io/cilium/brand-new", "tag": "v0.1.0"}},
    }
    history = HistoryConfig(last_pack_version="1.19.5", images={"spire-agent": "1.15.1"})

    report = prepare(
        pack_version="1.20.0",
        chart_values=chart_values,
        chart_source="fixture",
        mapping=_mapping(),
        history=history,
    )

    by_name = {item.name: item for item in report.images}
    assert by_name["cilium"].tag == "1.20.0"
    assert by_name["cilium"].tag_source == "chart"
    assert by_name["cilium-envoy"].tag == "1.20.0"
    assert by_name["cilium-envoy"].tag_source == "pack_version"
    assert by_name["spire-agent"].tag == "1.15.1"
    assert by_name["spire-agent"].tag_source == "history"
    assert len(report.new_chart_images) == 1
    assert report.new_chart_images[0].source_path == "brandNew.image"
    assert not report.ok

    fragment = report_to_pack_images_yaml(report)
    assert "packs/cilium/1.20.0/cilium:1.20.0" in fragment
    assert "cilium-envoy:1.20.0" in fragment

    assert report_to_names_payload(report) == {
        "images": ["cilium", "cilium-envoy", "spire-agent"],
    }
    detailed = report_to_detailed_payload(report)
    assert detailed["pack_version"] == "1.20.0"
    assert detailed["images"][0]["name"] == "cilium"
    assert detailed["images"][0]["tag"] == "1.20.0"
    assert detailed["new_images"][0]["path"] == "brandNew.image"


def test_prepare_cli_with_local_chart(tmp_path: Path) -> None:
    chart = tmp_path / "values.yaml"
    mapping = tmp_path / "mapping.yaml"
    history = tmp_path / "history.yaml"
    output = tmp_path / "images.yaml"

    chart.write_text(
        yaml.safe_dump({"image": {"repository": "quay.io/cilium/cilium", "tag": "v1.20.1"}}),
        encoding="utf-8",
    )
    mapping.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "normalize_tags": True,
                "images": {
                    "cilium": {
                        "chart_paths": ["image"],
                        "pack_tag": {"source": "chart"},
                    }
                },
                "ignore_chart_paths": [],
            }
        ),
        encoding="utf-8",
    )
    history.write_text(
        yaml.safe_dump({"version": 1, "last_pack_version": "1.19.5", "images": {}}),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "prepare",
            "--version",
            "1.20.1",
            "--mapping",
            str(mapping),
            "--history",
            str(history),
            "--chart-values",
            str(chart),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "1.20.1/cilium:1.20.1" in output.read_text(encoding="utf-8")
    updated = yaml.safe_load(history.read_text(encoding="utf-8"))
    assert updated["last_pack_version"] == "1.20.1"
    assert updated["images"]["cilium"] == "1.20.1"


def test_prepare_cli_skips_history_on_new_images(tmp_path: Path) -> None:
    chart = tmp_path / "values.yaml"
    mapping = tmp_path / "mapping.yaml"
    history = tmp_path / "history.yaml"

    chart.write_text(
        yaml.safe_dump(
            {
                "image": {"repository": "quay.io/cilium/cilium", "tag": "v1.20.1"},
                "extra": {"image": {"repository": "quay.io/cilium/extra", "tag": "1"}},
            }
        ),
        encoding="utf-8",
    )
    mapping.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "normalize_tags": True,
                "images": {
                    "cilium": {
                        "chart_paths": ["image"],
                        "pack_tag": {"source": "chart"},
                    }
                },
                "ignore_chart_paths": [],
            }
        ),
        encoding="utf-8",
    )
    history.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "last_pack_version": "1.19.5",
                "images": {"cilium": "1.19.5"},
            }
        ),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "prepare",
            "--version",
            "1.20.1",
            "--mapping",
            str(mapping),
            "--history",
            str(history),
            "--chart-values",
            str(chart),
        ],
    )
    assert result.exit_code == 1, result.output
    unchanged = yaml.safe_load(history.read_text(encoding="utf-8"))
    assert unchanged["last_pack_version"] == "1.19.5"
    assert unchanged["images"]["cilium"] == "1.19.5"


def test_prepare_cli_json_formats(tmp_path: Path) -> None:
    chart = tmp_path / "values.yaml"
    mapping = tmp_path / "mapping.yaml"
    history = tmp_path / "history.yaml"
    names_out = tmp_path / "names.json"
    detailed_out = tmp_path / "detailed.json"

    chart.write_text(
        yaml.safe_dump({"image": {"repository": "quay.io/cilium/cilium", "tag": "v1.20.1"}}),
        encoding="utf-8",
    )
    mapping.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "normalize_tags": True,
                "images": {
                    "cilium": {
                        "chart_paths": ["image"],
                        "pack_tag": {"source": "chart"},
                    }
                },
                "ignore_chart_paths": [],
            }
        ),
        encoding="utf-8",
    )
    history.write_text(
        yaml.safe_dump({"version": 1, "last_pack_version": "1.19.5", "images": {}}),
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "prepare",
            "--version",
            "1.20.1",
            "--mapping",
            str(mapping),
            "--history",
            str(history),
            "--chart-values",
            str(chart),
            "--format",
            "names",
            "--names-output",
            str(names_out),
            "--detailed-output",
            str(detailed_out),
            "--no-write-history",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(names_out.read_text(encoding="utf-8")) == {"images": ["cilium"]}
    detailed = json.loads(detailed_out.read_text(encoding="utf-8"))
    assert detailed["pack_version"] == "1.20.1"
    assert detailed["images"][0]["tag"] == "1.20.1"
    assert '"images"' in result.output
    assert '"cilium"' in result.output
