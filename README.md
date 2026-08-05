# BlobFront

A lightweight, open-source alternative to Azure Front Door for serving static websites hosted in Azure Blob Storage with custom domains and automatic HTTPS.

## Why BlobFront?

Azure Blob Storage's static website hosting is cheap and reliable, but adding custom domains with HTTPS requires Azure Front Door or Azure CDN — both of which add significant cost and complexity. BlobFront solves this with:

- **Automatic HTTPS** via Let's Encrypt (zero config)
- **Response caching** for CDN-like performance
- **Simple YAML config** to map domains → blob storage backends
- **Deploys to a single cheap Azure VM** (~$4/month on B1s)

## Architecture

```
[Browser] → [BlobFront (Caddy + Cache)] → [Azure Blob Storage Static Website]
                  ↕
          [Let's Encrypt]
```

Caddy handles TLS termination, reverse proxying, and response caching. A Python script generates the Caddyfile from your `config.yaml`.

## Quick Start

### 1. Configure your sites

Edit `config.yaml`:

```yaml
global:
  email: you@example.com  # For Let's Encrypt notifications
  cache_max_size: 512MB

sites:
  - domain: example.com
    backend: https://myaccount.z6.web.core.windows.net
    cache_ttl: 3600        # Cache responses for 1 hour
    cache_stale: 86400     # Serve stale content for up to 24h if backend is down

  - domain: blog.example.com
    backend: https://myblogaccount.z6.web.core.windows.net
    cache_ttl: 7200
```

> **Note:** Use the *static website endpoint* (`*.z6.web.core.windows.net`), not the blob endpoint.

### 2. Run locally (for testing)

```bash
docker compose up --build
```

This starts BlobFront on ports 80/443. For local testing, Caddy will use self-signed certs.

### 3. Deploy to Azure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your settings
terraform init
terraform apply
```

### 4. Point your DNS

Create A records pointing your custom domains to the VM's public IP (shown in Terraform output).

Caddy will automatically obtain and renew Let's Encrypt certificates once DNS resolves.

## Configuration Reference

### `config.yaml`

| Field | Description | Default |
|---|---|---|
| `global.email` | Let's Encrypt contact email | *required* |
| `global.cache_max_size` | Max disk cache size | `512MB` |
| `sites[].domain` | Custom domain | *required* |
| `sites[].backend` | Blob storage static website URL | *required* |
| `sites[].cache_ttl` | Cache TTL in seconds | `3600` |
| `sites[].cache_stale` | Stale cache TTL in seconds | `86400` |
| `sites[].headers` | Custom response headers (map) | `{}` |
| `sites[].redirect_www` | Redirect www subdomain | `false` |

## Cost Comparison

| Solution | Monthly Cost (approx) |
|---|---|
| Azure Front Door | $35+ (base) + per-request fees |
| Azure CDN (Standard) | $10–25+ |
| **BlobFront on B1ls VM (pay-as-you-go, default)** | **~$9 / £8–10** |
| **BlobFront on B1s VM (pay-as-you-go)** | **~$13 / £11–15** |
| **BlobFront on B1ls VM (1-yr reservation)** | **~$6 / £5–7** |

> **Reality check.** A single always-on Azure VM with a public IP has a hard
> floor. At pay-as-you-go rates in `uksouth`, the bill breaks down roughly as:
>
> | Item | ~Cost/mo (ex-VAT) |
> |---|---|
> | `Standard_B1s` compute | ~$7.60 |
> | Standard static public IP | ~$3.65 |
> | 30 GB Standard HDD OS disk | ~$1.55 |
> | Egress (first 100 GB free) | ~$0–1 |
> | **Total** | **~$13** |
>
> Add UK VAT (20%) and you land at **£11–15/month** — which is why the bill is
> higher than a naive "$4" estimate. The public IP is now a paid resource and
> can't be avoided for a single reachable VM.
>
> **To get the bill down:**
> - **Use a smaller VM.** The Terraform default is now `Standard_B1ls`
>   (0.5 GiB, ~$3.8/mo), viable because the image is **pre-built in CI** — the
>   VM only pulls it and never compiles Caddy. If the container is OOM-killed
>   under load, bump `vm_size` to `Standard_B1s` or `Standard_B2ts_v2` (1 GiB)
>   in `terraform.tfvars`.
> - **Buy a 1-year VM reservation or Azure Savings Plan** (~40% off compute) —
>   the biggest safe win on top of the smaller SKU. Purchased in the Azure
>   portal, not via this Terraform.
> - **Spot VM** is ~75% cheaper but can be evicted with 30s notice (downtime).

## Project Structure

```
blobfront/
├── config.yaml              # Your site configuration
├── docker-compose.yml       # Local development / deployment
├── Dockerfile               # Builds custom Caddy with cache plugin
├── scripts/
│   ├── generate_caddyfile.py  # Converts config.yaml → Caddyfile
│   └── entrypoint.sh         # Docker entrypoint
├── tests/
│   └── test_generate_caddyfile.py  # pytest suite for the generator
├── terraform/
│   ├── main.tf              # Azure VM + networking
│   ├── variables.tf         # Input variables
│   ├── outputs.tf           # Public IP, SSH info
│   ├── cloud-init.yaml      # VM bootstrap script
│   └── terraform.tfvars.example
└── .github/
    └── workflows/
        ├── ci.yml          # Tests + Caddyfile validation (push/PR)
        └── deploy.yml      # Build image → GHCR → deploy to VM (push to main)
```

## Development

The Caddyfile generator is the only piece of logic, and it has a test suite:

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/
```

Validating that Caddy actually accepts the generated config requires the
**custom-built binary** (stock `caddy validate` doesn't know the `cache`
directive), so do it inside the image:

```bash
docker build -t blobfront:ci .
docker run --rm --entrypoint /bin/sh blobfront:ci -c \
  'python3 /opt/blobfront/scripts/generate_caddyfile.py /etc/blobfront/config.yaml /tmp/Caddyfile \
   && caddy validate --config /tmp/Caddyfile'
```

Both steps run automatically in CI (`.github/workflows/ci.yml`) on every push
and pull request.

## Advanced Usage

### Custom Headers

```yaml
sites:
  - domain: example.com
    backend: https://myaccount.z6.web.core.windows.net
    headers:
      X-Frame-Options: DENY
      X-Content-Type-Options: nosniff
      Content-Security-Policy: "default-src 'self'"
```

### WWW Redirect

```yaml
sites:
  - domain: example.com
    backend: https://myaccount.z6.web.core.windows.net
    redirect_www: true  # www.example.com → example.com
```

### Health Check

BlobFront exposes a health endpoint at `http://localhost:2019/config/` (Caddy admin API, bound to localhost only).

## Prebuilt image (CI/CD)

The custom Caddy binary is compiled **once in GitHub Actions** and pushed to
GitHub Container Registry, instead of being built on the VM. This means the VM
only *pulls* a ready image — so it needs far less RAM and can run on the
cheapest SKUs.

- Workflow: `.github/workflows/deploy.yml` (builds on push to `main`, then
  pulls + restarts on the VM over SSH).
- Required secrets: `VM_HOST`, `VM_USER`, `VM_SSH_KEY`.
- One-time: after the first build, set the GHCR package visibility to **Public**
  so the VM can pull without credentials (or add `docker login ghcr.io` to the
  deploy step).
- If you fork, set the `IMAGE` env var (or edit the default in
  `docker-compose.yml`) to point at your own `ghcr.io/<owner>/blobfront`.

## Updating Configuration

After editing `config.yaml`:

```bash
# Local — entrypoint regenerates the Caddyfile on start
docker compose restart

# On the VM (via SSH) — config.yaml is mounted, so just restart to regenerate
cd /opt/blobfront
git pull
docker compose up -d
```

> The Caddyfile lives **inside** the container at `/etc/caddy/Caddyfile` and is
> regenerated from `config.yaml` on every start, so running the generator on the
> host has no effect — restart the container instead.

## License

MIT
