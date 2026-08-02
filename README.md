# misc-scripts

Small operational tools. Each Python project uses [`uv`](https://docs.astral.sh/uv/).

## Projects

| Path | Purpose |
|------|---------|
| [`cilium-pack-images/`](cilium-pack-images/) | Resolve Cilium pack image names/tags from upstream Helm chart + history |
| [`dhi-catalog-check/`](dhi-catalog-check/) | Verify those tags exist on Docker Hardened Images (`dhi.io`) |
| [`dhi-registry-sync/`](dhi-registry-sync/) | Dry-run / dispatch GAR sync workflow for images that passed DHI lookup |
| [`cleanup-edge-hosts.sh`](cleanup-edge-hosts.sh) | Clean Portworx leftovers on Kairos/edge nodes over SSH |

Typical Cilium → DHI → GAR flow:

```text
cilium-pack-images  →  dhi-catalog-check  →  dhi-registry-sync (dry-run → --execute)
```

---

## cilium-pack-images

Fetch upstream Cilium Helm `values.yaml` for a version, map chart images to pack metadata names, resolve tags (chart / pack version / history), and detect new upstream images.

```bash
cd cilium-pack-images
uv sync

# Primary: only the version number is required
uv run cilium-pack-images prepare --version 1.20.0

# JSON: names only
uv run cilium-pack-images prepare --version 1.20.0 --format names

# JSON: names + versions
uv run cilium-pack-images prepare --version 1.20.0 --format detailed \
  --detailed-output /tmp/pack-detailed.json
```

On success, updates `history.yaml` automatically (use `--no-write-history` to skip).

See [cilium-pack-images/README.md](cilium-pack-images/README.md).

---

## dhi-catalog-check

For a Cilium version, resolve pack images then check each `dhi.io/<name>:<tag>` via `docker manifest inspect`.

**Prereqs:** Colima (or compatible Docker client), already `docker login` to Docker Hub. No credentials in this repo.

```bash
cd dhi-catalog-check
uv sync
colima start   # if needed
docker context show   # expect colima

uv run dhi-catalog-check verify --version 1.20.0 --output /tmp/dhi-verify.json
```

JSON includes `present`, `missing`, and `all_present`.

See [dhi-catalog-check/README.md](dhi-catalog-check/README.md).

---

## dhi-registry-sync

Dispatch [`self-service-registry-sync.yml`](https://github.com/spectrocloud/hardened-images/actions/workflows/self-service-registry-sync.yml) for each image that **passed** DHI lookup.

**Dry-run is the default** (no GitHub Actions runners). Use `--execute` only after review. Default delay between real dispatches: **30s**.

```bash
cd dhi-registry-sync
uv sync

# Review plan (no runners)
uv run dhi-registry-sync sync \
  --version 1.20.0 \
  --verify-report /tmp/dhi-verify.json \
  --output /tmp/sync-plan.json

# After review: dispatch workflows
uv run dhi-registry-sync sync \
  --version 1.20.0 \
  --verify-report /tmp/dhi-verify.json \
  --execute

# If some tags are missing from DHI but you still want to sync the rest:
uv run dhi-registry-sync sync \
  --version 1.20.0 \
  --verify-report /tmp/dhi-verify.json \
  --allow-partial \
  --execute
```

Requires `gh` authenticated to `spectrocloud/hardened-images` for `--execute`.

See [dhi-registry-sync/README.md](dhi-registry-sync/README.md).

---

## cleanup-edge-hosts.sh

SSH into Kairos/edge hosts and remove Portworx host leftovers. Requires `sshpass`.

```bash
./cleanup-edge-hosts.sh <ip> [ip...]
SSH_USER=kairos SSH_PASS=kairos ./cleanup-edge-hosts.sh 10.10.141.177
```

---

## Security notes

- Do not commit Docker Hub tokens, `.env` files, or credential paths.
- DHI tools assume local `docker login` / `gh` auth; they do not embed secrets.
- Ignore local artifacts: `.venv/`, `.cache/`, `.coverage` (per-project `.gitignore`).
