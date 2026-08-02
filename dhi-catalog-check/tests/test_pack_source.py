from dhi_catalog_check.pack_source import images_from_detailed_payload


def test_images_from_detailed_payload() -> None:
    payload = {
        "pack_version": "1.19.6",
        "images": [
            {"name": "cilium", "tag": "1.19.6"},
            {"name": "busybox", "tag": "1.37"},
        ],
    }
    assert images_from_detailed_payload(payload) == [
        ("cilium", "1.19.6"),
        ("busybox", "1.37"),
    ]
