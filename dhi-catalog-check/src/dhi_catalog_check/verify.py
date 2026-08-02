from concurrent.futures import ThreadPoolExecutor, as_completed

from dhi_catalog_check.docker_lookup import LookupResult, build_ref, manifest_exists
from dhi_catalog_check.models import ImageCheck, VerifyReport


def verify_images(
    images: list[tuple[str, str]],
    *,
    pack_version: str,
    registry: str = "dhi.io",
    docker_bin: str = "docker",
    max_workers: int = 8,
) -> VerifyReport:
    """Check each (name, tag) against the DHI registry via docker manifest inspect."""
    if not images:
        return VerifyReport(
            pack_version=pack_version,
            registry=registry,
            all_present=True,
            present=[],
            missing=[],
            checked=0,
        )

    def check_one(name: str, tag: str) -> ImageCheck:
        ref = build_ref(name, tag, registry=registry)
        result: LookupResult = manifest_exists(ref, docker_bin=docker_bin)
        return ImageCheck(
            name=name,
            tag=tag,
            ref=ref,
            present=result.present,
            reason=None if result.present else result.reason,
        )

    checks: list[ImageCheck] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(check_one, name, tag): (name, tag) for name, tag in images}
        for future in as_completed(futures):
            checks.append(future.result())

    # Stable order matching input list
    by_key = {(item.name, item.tag): item for item in checks}
    ordered = [by_key[(name, tag)] for name, tag in images]
    present = [item for item in ordered if item.present]
    missing = [item for item in ordered if not item.present]
    return VerifyReport(
        pack_version=pack_version,
        registry=registry,
        all_present=not missing,
        present=present,
        missing=missing,
        checked=len(ordered),
    )
