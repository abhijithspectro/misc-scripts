# dhi-catalog-check

Verify that Cilium pack image names/tags from [`cilium-pack-images`](../cilium-pack-images) exist in the Docker Hardened Images catalog (`dhi.io`).

## Security (public repo)

- **Never** commit Docker Hub tokens, username files, or `.env` secrets.
- This tool **does not** read credential files and **does not** accept password/token flags.
- Assumes you are already logged in (`docker login`) via your Docker client (**Colima** on macOS — not Docker Desktop).
- Lookup uses `docker manifest inspect` only; error text is sanitized before display.

## Setup

```bash
cd dhi-catalog-check
uv sync
```

Ensure Colima is running and you are logged in to Docker Hub:

```bash
colima start
docker context show   # should be colima
docker login          # interactive / already authenticated
```

## Usage

```bash
uv run dhi-catalog-check verify --version 1.19.6
```

Flow:

1. Calls `cilium-pack-images` to resolve the named + versioned image list for that Cilium version
2. For each `name:tag`, checks `dhi.io/<name>:<tag>` via `docker manifest inspect`
3. Prints JSON summary with `present`, `missing`, and `all_present`

### Example JSON

```json
{
  "pack_version": "1.19.6",
  "registry": "dhi.io",
  "all_present": true,
  "present": [
    {
      "name": "cilium",
      "tag": "1.19.6",
      "ref": "dhi.io/cilium:1.19.6",
      "present": true,
      "reason": null
    }
  ],
  "missing": [],
  "checked": 16
}
```

### Options

```bash
# Human table
uv run dhi-catalog-check verify --version 1.19.6 --format human

# Write report file
uv run dhi-catalog-check verify --version 1.19.6 --output /tmp/dhi-report.json

# Reuse a prior cilium-pack-images detailed JSON (skip chart fetch)
uv run cilium-pack-images prepare --version 1.19.6 --format detailed --no-write-history \
  > /tmp/pack-detailed.json
uv run dhi-catalog-check verify --version 1.19.6 --detailed-input /tmp/pack-detailed.json
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | All images present (`all_present: true`) |
| 1 | One or more missing (unless `--no-fail-on-missing`) |
| 2 | Usage / pack resolution error |

## Tests

```bash
uv run pytest
```
