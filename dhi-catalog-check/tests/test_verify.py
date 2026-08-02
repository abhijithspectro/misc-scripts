from unittest.mock import patch

from dhi_catalog_check.docker_lookup import LookupResult
from dhi_catalog_check.verify import verify_images


def test_verify_images_splits_present_and_missing() -> None:
    def fake_manifest(ref: str, **_kwargs: object) -> LookupResult:
        if ref.endswith("cilium:1.19.6"):
            return LookupResult(ref=ref, present=True)
        return LookupResult(ref=ref, present=False, reason="not_found")

    with patch("dhi_catalog_check.verify.manifest_exists", side_effect=fake_manifest):
        report = verify_images(
            [("cilium", "1.19.6"), ("missing-img", "9.9.9")],
            pack_version="1.19.6",
            max_workers=2,
        )

    assert report.checked == 2
    assert report.all_present is False
    assert [item.name for item in report.present] == ["cilium"]
    assert [item.name for item in report.missing] == ["missing-img"]
    assert report.missing[0].reason == "not_found"


def test_verify_images_all_present_flag() -> None:
    with patch(
        "dhi_catalog_check.verify.manifest_exists",
        side_effect=lambda ref, **_k: LookupResult(ref=ref, present=True),
    ):
        report = verify_images([("cilium", "1.19.6")], pack_version="1.19.6")
    assert report.all_present is True
    assert report.missing == []
