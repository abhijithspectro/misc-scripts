# dhi-registry-sync

Plan (and optionally dispatch) the
[`self-service-registry-sync.yml`](https://github.com/spectrocloud/hardened-images/actions/workflows/self-service-registry-sync.yml)
workflow for every Cilium pack image that **passed** `dhi-catalog-check`.

## Safety

- **Dry-run is the default.** No `gh workflow run` is issued unless you pass `--execute`.
- Unit tests **never** call the real GitHub API / runners (dispatcher is mocked or dry-run).
- Do not run `--execute` until you have reviewed the plan.

## Setup

```bash
cd dhi-registry-sync
uv sync
```

Requires `gh` authenticated to `spectrocloud/hardened-images` when using `--execute`.

## Usage (review first)

```bash
# 1) Optional: produce a verify report once
uv run --project ../dhi-catalog-check dhi-catalog-check verify \
  --version 1.19.6 --output /tmp/dhi-verify.json

# 2) Dry-run sync plan from that report (NO runners)
uv run dhi-registry-sync sync \
  --version 1.19.6 \
  --verify-report /tmp/dhi-verify.json \
  --output /tmp/sync-plan.json
```

Or resolve pack images + DHI lookup in one dry-run:

```bash
uv run dhi-registry-sync sync --version 1.19.6
```

## Execute (only after review)

```bash
uv run dhi-registry-sync sync \
  --version 1.19.6 \
  --verify-report /tmp/dhi-verify.json \
  --execute
```

This dispatches one workflow run per **present** image name (`dhi_repository` input),
with a **30s delay between consecutive dispatches** by default (`--delay-seconds 30`).
Dry-run never sleeps. Missing DHI images are skipped. With `--require-all-present`
(default), the command refuses to proceed if the verify report has any missing images.

## Tests

```bash
uv run pytest
```
