import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from dhi_catalog_check.models import ImageCheck, VerifyReport

from dhi_registry_sync.cli import main


def _report() -> VerifyReport:
    return VerifyReport(
        pack_version="1.19.6",
        registry="dhi.io",
        all_present=True,
        present=[
            ImageCheck(
                name="cilium",
                tag="1.19.6",
                ref="dhi.io/cilium:1.19.6",
                present=True,
            )
        ],
        missing=[],
        checked=1,
    )


def test_cli_dry_run_default_does_not_use_gh(tmp_path: Path) -> None:
    report_path = tmp_path / "verify.json"
    report_path.write_text(_report().model_dump_json(), encoding="utf-8")
    out = tmp_path / "plan.json"

    with patch("dhi_registry_sync.cli.GhWorkflowDispatcher") as gh_cls:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "sync",
                "--version",
                "1.19.6",
                "--verify-report",
                str(report_path),
                "--output",
                str(out),
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, result.output
        gh_cls.assert_not_called()

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["results"][0]["dispatched"] is False
    assert payload["results"][0]["dry_run"] is True
    assert "No GitHub Actions runners were used" in result.output or payload["dry_run"]


def test_cli_execute_uses_dispatcher_but_test_injects_dry_run(tmp_path: Path) -> None:
    """Ensure --execute path constructs GhWorkflowDispatcher (still mocked; no real run)."""
    report_path = tmp_path / "verify.json"
    report_path.write_text(_report().model_dump_json(), encoding="utf-8")

    class FakeGh:
        def dispatch(self, *, repo: str, workflow: str, dhi_repository: str):
            from dhi_registry_sync.models import DispatchResult

            return DispatchResult(
                dhi_repository=dhi_repository,
                dispatched=True,
                dry_run=False,
                detail="fake",
            )

    with patch("dhi_registry_sync.cli.GhWorkflowDispatcher", return_value=FakeGh()):
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "sync",
                "--version",
                "1.19.6",
                "--verify-report",
                str(report_path),
                "--execute",
                "--format",
                "json",
            ],
        )
    assert result.exit_code == 0, result.output
    assert '"dispatched": true' in result.output
