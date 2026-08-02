import pytest

from cilium_pack_images.extract import extract_chart_images, extract_pack_images, get_by_path, parse_image_ref


def test_extract_pack_images_errors() -> None:
    with pytest.raises(ValueError, match=r"pack\.content\.images"):
        extract_pack_images({})
    with pytest.raises(ValueError, match="must be a list"):
        extract_pack_images({"pack": {"content": {"images": {}}}})
    with pytest.raises(ValueError, match="image key"):
        extract_pack_images({"pack": {"content": {"images": ["bad"]}}})


def test_parse_image_ref_errors() -> None:
    with pytest.raises(ValueError, match="missing tag"):
        parse_image_ref("repo/name")
    with pytest.raises(ValueError, match="digest"):
        parse_image_ref("repo/name@sha256:abc")


def test_extract_chart_images_nested_and_empty() -> None:
    values = {
        "image": {"repository": "quay.io/cilium/cilium", "tag": "v1"},
        "standaloneDnsProxy": {"image": {"repository": "", "tag": ""}},
        "items": [{"image": {"repository": "quay.io/cilium/x", "tag": "1"}}],
    }
    images = extract_chart_images(values)
    paths = {img.source_path for img in images}
    assert "image" in paths
    assert "standaloneDnsProxy.image" in paths
    assert "items[0].image" in paths


def test_get_by_path() -> None:
    data = {"a": {"b": {"c": 1}}}
    assert get_by_path(data, "a.b.c") == 1
    with pytest.raises(KeyError):
        get_by_path(data, "a.x")
