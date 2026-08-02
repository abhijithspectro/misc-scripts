# cilium-pack-images

Prepare and audit Spectro Cloud Cilium pack image metadata from upstream Cilium Helm charts.

For a future pack bump you should only need the **version number**. The tool:

1. Fetches upstream `values.yaml` for that Cilium version
2. Resolves pack image tags using historical mapping + tag policy
3. Detects **new** upstream image blocks not covered by the mapping

## Setup

```bash
cd cilium-pack-images
uv sync
```

## Prepare a pack version (primary workflow)

```bash
uv run cilium-pack-images prepare --version 1.19.5
```

What it does:

- Downloads  
  `https://raw.githubusercontent.com/cilium/cilium/v{version}/install/kubernetes/cilium/values.yaml`  
  (cached under `.cache/charts/`)
- Applies [`mapping.yaml`](mapping.yaml) associations and tag policies
- Reads historical tags from [`history.yaml`](history.yaml) when policy is `history`
- Prints a suggested `pack.content.images` fragment
- On success (no new unmapped images), updates `history.yaml` automatically
- Exits `1` if upstream added unmapped images (history is left unchanged)

### JSON outputs

Two JSON shapes are supported:

**Names** (`--format names`) — image names only:
```json
{"images": ["cilium", "cilium-certgen", "hubble-relay"]}
```

**Detailed** (`--format detailed`) — names plus version metadata:
```json
{
  "pack_version": "1.20.0",
  "chart_source": "https://raw.githubusercontent.com/cilium/cilium/v1.20.0/...",
  "images": [
    {
      "name": "cilium",
      "tag": "1.20.0",
      "tag_source": "chart",
      "chart_path": "image",
      "chart_tag": "v1.20.0",
      "image": "us-docker.pkg.dev/.../cilium:1.20.0"
    }
  ],
  "new_images": [],
  "notes": []
}
```

Write both files in one run:
```bash
uv run cilium-pack-images prepare --version 1.20.0 \
  --names-output /tmp/names.json \
  --detailed-output /tmp/detailed.json
```

Useful flags:

```bash
# Write pack.content.images YAML fragment
uv run cilium-pack-images prepare --version 1.20.0 --output /tmp/images.yaml

# Dry-run: do not update history.yaml
uv run cilium-pack-images prepare --version 1.20.0 --no-write-history

# Seed history from a previous pack instead of history.yaml
uv run cilium-pack-images prepare --version 1.20.0 \
  --previous-pack-values /path/to/cilium_oss_1.19.5/values.yaml

# Offline / use a local chart checkout
uv run cilium-pack-images prepare --version 1.20.0 \
  --chart-values /path/to/charts/cilium/values.yaml
```

### Tag policy (`mapping.yaml`)

| `pack_tag.source` | Meaning |
|---|---|
| `chart` | Use upstream chart tag (strip leading `v`) |
| `pack_version` | Use the version passed to `--version` (e.g. envoy) |
| `history` | Keep tag from `history.yaml` / previous pack |
| `pinned` | Fixed `pack_tag.value` |

When upstream adds a new image:

1. Tool reports `New upstream image blocks`
2. Add a mapping entry (name + `chart_paths` + `pack_tag` policy)
3. Re-run `prepare --version …`
4. Copy the printed `pack.content.images` into the pack

## Compare local files

```bash
uv run cilium-pack-images compare \
  --pack-values /path/to/pack/values.yaml \
  --chart-values /path/to/charts/cilium/values.yaml
```

## Tests

```bash
uv run pytest
```
