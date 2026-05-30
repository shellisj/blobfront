# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

BlobFront is a self-hosted, open-source alternative to Azure Front Door / Azure CDN for
serving Azure Blob Storage **static website** endpoints over custom domains with automatic
HTTPS and response caching. It is **deployment infrastructure**, not an application: there is
no compiled code, no package manifest (`package.json`/`pyproject.toml`), and no test suite.
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
- **`scripts/generate_caddyfile.py`** — reads `config.yaml` (via `CONFIG_PATH`) and emits a
  Caddyfile (to `CADDYFILE_PATH`). `build_global()` produces the global block (Let's Encrypt
  email + cache-handler config); `build_site()` produces one site block per entry in `sites`,
  wiring up `reverse_proxy`, per-site `cache`, header rewriting, logging, and error handling.
- **`scripts/entrypoint.sh`** — the container entrypoint. Runs the generator, prints the
  generated Caddyfile (for debugging), creates `/var/log/caddy`, runs `caddy validate`, then
  `exec caddy run`. **The Caddyfile is regenerated on every container start** — this is the
  mechanism by which config changes take effect.
- **`Dockerfile`** — two stages: (1) `xcaddy build` a custom Caddy binary with the
  `github.com/caddyserver/cache-handler` plugin; (2) `python:3.12-slim` runtime with `pyyaml`,
  the custom Caddy binary, and the scripts. Defines `CONFIG_PATH` and `CADDYFILE_PATH`.
- **`docker-compose.yml`** — single `caddy` service. Persists Let's Encrypt certs in the
  `caddy_data` volume; mounts `config.yaml` read-only; exposes 80/443.
- **`terraform/`** — Azure IaC that provisions a single cheap Linux VM (Ubuntu 24.04,
  `Standard_B1s` by default) plus networking/NSG. `cloud-init.yaml` installs Docker and clones
  the repo to `/opt/blobfront`.
- **`.github/workflows/deploy.yml`** — optional CD. On push to `main` touching `config.yaml`,
  `Dockerfile`, `scripts/**`, or `docker-compose.yml`, it SSHes into the VM, pulls, rebuilds,
  and reloads Caddy.

## Commands

There is no build/lint/test toolchain. Work with the Docker and Terraform lifecycle:

```bash
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

The generator depends only on `pyyaml`. Validating output end-to-end realistically means
building the image (`docker compose build`) since the entrypoint runs the generator + validate.

## Conventions and gotchas

- **Backends must be the static website endpoint** (`*.z6.web.core.windows.net`), not the blob
  endpoint. The generator rewrites the upstream `Host` header to the backend host and adds
  `X-Forwarded-Host`, which is what makes Azure static website serving work.
- **The generated Caddyfile path is `/etc/caddy/Caddyfile`** and only exists *inside* the
  container. The README's "on VM" snippet that runs `python3 scripts/generate_caddyfile.py` on
  the host won't write there — prefer `docker compose restart` (regenerates on start) or
  `docker compose exec caddy caddy reload ...` after the in-container file is regenerated.
- **`global.cache_max_size` in `config.yaml` is currently not wired into the generated
  Caddyfile.** `build_global()` reads it but does not emit a corresponding directive. If you
  touch cache behavior, this is the place to address it.
- **Per-site behavior is generated, not hand-written.** To change how every site is rendered
  (headers stripped, log rotation, error handler, redirect format), edit `build_site()` rather
  than any Caddyfile — Caddyfiles in this repo are always machine output.
- **Azure response headers (`x-ms-request-id`, `x-ms-version`) and `Server` are stripped** from
  responses by default in `build_site()`.
- **Terraform defaults are permissive for convenience:** `allowed_ssh_cidr` defaults to
  `0.0.0.0/0` — restrict it for real deployments. `cloud-init.yaml` clones from a placeholder
  `https://github.com/YOUR_USERNAME/blobfront.git`; update it (or the fork URL) before relying on
  auto-bootstrap.
- **Real TLS requires public DNS** pointing at the VM's public IP before Caddy can obtain
  Let's Encrypt certs; local runs fall back to internal certs.
- **Python style:** the generator uses `snake_case`, builds Caddyfile blocks as lists of
  indented strings joined with `\n`, and is driven entirely by `CONFIG_PATH`/`CADDYFILE_PATH`
  environment variables (defaults `/etc/blobfront/config.yaml` and `/etc/caddy/Caddyfile`).
