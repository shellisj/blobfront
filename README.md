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
| **BlobFront on B1s VM** | **~$4** |

## Project Structure

```
blobfront/
├── config.yaml              # Your site configuration
├── docker-compose.yml       # Local development / deployment
├── Dockerfile               # Builds custom Caddy with cache plugin
├── scripts/
│   ├── generate_caddyfile.py  # Converts config.yaml → Caddyfile
│   └── entrypoint.sh         # Docker entrypoint
├── terraform/
│   ├── main.tf              # Azure VM + networking
│   ├── variables.tf         # Input variables
│   ├── outputs.tf           # Public IP, SSH info
│   ├── cloud-init.yaml      # VM bootstrap script
│   └── terraform.tfvars.example
└── .github/
    └── workflows/
        └── deploy.yml       # Optional CI/CD pipeline
```

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

## Updating Configuration

After editing `config.yaml`, regenerate the Caddyfile and reload:

```bash
# Local
docker compose restart

# On VM (via SSH)
cd /opt/blobfront
python3 scripts/generate_caddyfile.py
docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## License

MIT
