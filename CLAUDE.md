# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

BlobFront is a self-hosted, open-source alternative to Azure Front Door / Azure CDN for
serving Azure Blob Storage **static website** endpoints over custom domains with automatic
HTTPS and response caching. It is **deployment infrastructure**, not an application: there is
no compiled code and no package manifest (`package.json`/`pyproject.toml`). The only logic is the
Python Caddyfile generator, which has a `pytest` suite under `tests/`.
The "product" is a Docker image running a custom Caddy build, configured from a single YAML file.

## Architecture

The entire system is a translation pipeline from declarative YAML to a running Caddy server:

```
config.yaml ──> scripts/generate_caddyfile.py ──> /etc/caddy/Caddyfile ──> caddy run
   (user edits)        (Python, at startup)           (generated)          (serves :80/:443)
```

Request path at runtime:

```
Browser ──> Caddy (TLS + cache-handler) ──> Azure Blob static website (*.z6.web.core.windows.net)
                  ↕
            Let's Encrypt
```

Key components and how they fit together:

- **`config.yaml`** — the single source of truth. Maps custom domains to blob backends and sets
  per-site cache TTLs, custom response headers, and www-redirect. This is the only file users
  normally edit. It is mounted **read-only** into the container at `/etc/blobfront/config.yaml`.
- **`scripts/generate_caddyfile.py`** — a single `generate_caddyfile(config_path, output_path)`
  function (CLI args, defaulting to `config.yaml`/`Caddyfile`). It builds the Caddyfile as a flat
  `lines` list: first a global options block (Let's Encrypt `email` + `order cache before rewrite`,
  which makes the cache-handler plugin run early), then one block per entry in `sites` wiring up
  `cache` (ttl/stale), `reverse_proxy`, header rewriting, logging, and `handle_errors`. It exits
  non-zero if the config is missing or `sites` is empty.
- **`scripts/entrypoint.sh`** — the container entrypoint. Runs the generator, prints the
  generated Caddyfile (for debugging), creates `/var/log/caddy`, runs `caddy validate`, then
  `exec caddy run`. **The Caddyfile is regenerated on every container start** — this is the
  mechanism by which config changes take effect.
- **`Dockerfile`** — two stages: (1) `xcaddy build` a custom Caddy binary with the
  `github.com/caddyserver/cache-handler` plugin; (2) `python:3.12-slim` runtime with `pyyaml`,
  the custom Caddy binary, and the scripts. Defines `CONFIG_PATH` and `CADDYFILE_PATH`.
- **`docker-compose.yml`** — single `caddy` service. Declares both `image:`
  (`ghcr.io/<owner>/blobfront`, overridable via the `IMAGE` env var) and `build: .`, so the VM
  *pulls* the prebuilt image while local `docker compose up --build` still builds from source.
  Persists Let's Encrypt certs in the `caddy_data` volume; mounts `config.yaml` read-only;
  exposes 80/443.
- **`terraform/`** — Azure IaC that provisions a single cheap Linux VM (Ubuntu 24.04,
  `Standard_B1s` by default) plus networking/NSG. `cloud-init.yaml` installs Docker and clones
  the repo to `/opt/blobfront`.
- **`.github/workflows/deploy.yml`** — CI/CD. On push to `main` touching the build inputs, a
  `build` job compiles the image once and pushes it to GHCR
  (`ghcr.io/<owner>/blobfront`), then a `deploy` job SSHes into the VM and runs `git pull` +
  `docker compose pull` + `docker compose up -d`. **The VM never compiles Caddy** — it only
  pulls the prebuilt image, which is what allows the smallest/cheapest VM SKUs.

## Commands

```bash
# Unit-test the generator (the only real logic). Needs pytest + pyyaml.
pip install -r requirements-dev.txt
python3 -m pytest -q tests/

# End-to-end Caddyfile validation must use the CUSTOM-built binary, because the
# `cache` directive is unknown to stock Caddy. Build the image, then generate +
# validate inside it (this is what CI does — see .github/workflows/ci.yml):
docker build -t blobfront:ci .
docker run --rm --entrypoint /bin/sh blobfront:ci -c \
  'python3 /opt/blobfront/scripts/generate_caddyfile.py /etc/blobfront/config.yaml /tmp/Caddyfile \
   && caddy validate --config /tmp/Caddyfile'

# Run locally for testing (uses internal/self-signed certs; no public DNS needed)
docker compose up --build

# Apply a config.yaml change locally — restart so the entrypoint regenerates the Caddyfile
docker compose restart

# Generate a Caddyfile on the host to eyeball the output (set paths to writable locations)
CONFIG_PATH=./config.yaml CADDYFILE_PATH=/tmp/Caddyfile python3 scripts/generate_caddyfile.py
cat /tmp/Caddyfile

# Validate a generated Caddyfile (requires a caddy binary; the entrypoint also does this)
caddy validate --config /tmp/Caddyfile

# Provision Azure infrastructure
cd terraform
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform apply

# On the VM: reload after a config change without a full restart
cd /opt/blobfront && docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

The generator depends only on `pyyaml`. `caddy validate` on stock Caddy will **reject** the
generated Caddyfile (it doesn't know the `cache` directive) — always validate against the image's
custom binary, as the CI `validate` job and the entrypoint do.

CI: `.github/workflows/ci.yml` runs the `pytest` suite and the build-and-validate step on every
push and pull request; `.github/workflows/deploy.yml` builds/ships the image only on push to
`main`.

## Conventions and gotchas

- **Backends must be the static website endpoint** (`*.z6.web.core.windows.net`), not the blob
  endpoint. The generator rewrites the upstream `Host` header to the backend host and adds
  `X-Forwarded-Host`, which is what makes Azure static website serving work.
- **The generated Caddyfile path is `/etc/caddy/Caddyfile`** and only exists *inside* the
  container. The README's "on VM" snippet that runs `python3 scripts/generate_caddyfile.py` on
  the host won't write there — prefer `docker compose restart` (regenerates on start) or
  `docker compose exec caddy caddy reload ...` after the in-container file is regenerated.
- **Caching is activated per-site**, not globally: the `order cache before rewrite` global line
  plus each site's `cache { ttl/stale }` block is what enables the cache-handler plugin (a global
  `cache {}` block is optional). `global.cache_ttl`/`cache_stale` set defaults for sites that omit
  them. There is deliberately **no max-size-in-MB knob** — the plugin's default store is bounded
  by entry count, not bytes, so don't add a `cache_max_size`-style directive without wiring a real
  storage backend (`nuts`/`badger`/`redis`) and validating with `caddy validate` first.
- **Per-site behavior is generated, not hand-written.** To change how every site is rendered
  (headers stripped, log rotation, error handler, redirect format), edit the site loop in
  `generate_caddyfile()` — Caddyfiles in this repo are always machine output.
- **Azure response headers (`x-ms-request-id`, `x-ms-version`, `x-ms-lease-status`,
  `x-ms-blob-type`) are always stripped** via `header_down`, and `Server` is stripped only when a
  site defines custom `headers` (it lives inside the optional `header` block).
- **Terraform defaults are permissive for convenience:** `allowed_ssh_cidr` defaults to
  `0.0.0.0/0` — restrict it for real deployments. `cloud-init.yaml` clones from a placeholder
  `https://github.com/YOUR_USERNAME/blobfront.git`; update it (or the fork URL) before relying on
  auto-bootstrap.
- **Real TLS requires public DNS** pointing at the VM's public IP before Caddy can obtain
  Let's Encrypt certs; local runs fall back to internal certs.
- **Python style:** the generator uses `snake_case`, builds Caddyfile blocks as lists of
  indented strings joined with `\n`, and is driven entirely by `CONFIG_PATH`/`CADDYFILE_PATH`
  environment variables (defaults `/etc/blobfront/config.yaml` and `/etc/caddy/Caddyfile`).
