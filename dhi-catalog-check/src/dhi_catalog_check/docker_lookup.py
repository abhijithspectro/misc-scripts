"""Look up image tags using the local Docker CLI (Colima-compatible).

Assumes the user is already logged in. This module never reads credential files,
never prints tokens, and sanitizes Docker CLI stderr before surfacing errors.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

# Strip anything that looks like a bearer/basic token if Docker ever echoes it.
_SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*\S+(?:\s+\S+)*"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]+"),
    re.compile(r"(?i)token\s*[:=]\s*\S+"),
    re.compile(r"(?i)password\s*[:=]\s*\S+"),
)


@dataclass(frozen=True)
class LookupResult:
    ref: str
    present: bool
    reason: str | None = None


def sanitize_error(text: str) -> str:
    cleaned = text.strip()
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("<redacted>", cleaned)
    # Keep message short; avoid dumping large blobs.
    if len(cleaned) > 300:
        cleaned = cleaned[:300] + "…"
    return cleaned


def build_ref(name: str, tag: str, *, registry: str = "dhi.io") -> str:
    return f"{registry}/{name}:{tag}"


def manifest_exists(
    ref: str,
    *,
    docker_bin: str = "docker",
    timeout: float = 120.0,
) -> LookupResult:
    """Return whether `docker manifest inspect REF` succeeds.

    Uses the active Docker context (e.g. Colima). Relies on existing `docker login`.
    """
    try:
        completed = subprocess.run(
            [docker_bin, "manifest", "inspect", ref],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError:
        return LookupResult(ref=ref, present=False, reason="docker_cli_not_found")
    except subprocess.TimeoutExpired:
        return LookupResult(ref=ref, present=False, reason="timeout")

    if completed.returncode == 0:
        return LookupResult(ref=ref, present=True)

    err = sanitize_error(completed.stderr or completed.stdout or "manifest inspect failed")
    lowered = err.lower()
    if "not found" in lowered or "does not exist" in lowered or "no such" in lowered:
        reason = "not_found"
    elif "denied" in lowered or "unauthorized" in lowered or "authentication required" in lowered:
        reason = "auth_required"
    else:
        reason = err or "inspect_failed"
    return LookupResult(ref=ref, present=False, reason=reason)
