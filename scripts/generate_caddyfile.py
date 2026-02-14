#!/usr/bin/env python3
"""
Generates a Caddyfile from config.yaml.
Usage: python3 generate_caddyfile.py [config_path] [output_path]
"""

import sys
import yaml
from pathlib import Path


def generate_caddyfile(config_path: str = "config.yaml", output_path: str = "Caddyfile") -> None:
    config_file = Path(config_path)
    if not config_file.exists():
        print(f"Error: {config_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(config_file) as f:
        config = yaml.safe_load(f)

    global_cfg = config.get("global", {})
    sites = config.get("sites", [])

    if not sites:
        print("Error: No sites defined in config", file=sys.stderr)
        sys.exit(1)

    email = global_cfg.get("email", "")
    cache_max_size = global_cfg.get("cache_max_size", "512MB")

    lines = []

    # Global options block
    lines.append("{")
    if email:
        lines.append(f"\temail {email}")
    lines.append("\torder cache before rewrite")
    lines.append("}")
    lines.append("")

    for site in sites:
        domain = site["domain"]
        backend = site["backend"].rstrip("/")
        cache_ttl = site.get("cache_ttl", 3600)
        cache_stale = site.get("cache_stale", 86400)
        headers = site.get("headers", {})
        redirect_www = site.get("redirect_www", False)

        # WWW redirect block
        if redirect_www:
            lines.append(f"www.{domain} {{")
            lines.append(f"\tredir https://{domain}{{uri}} permanent")
            lines.append("}")
            lines.append("")

        # Main site block
        lines.append(f"{domain} {{")

        # Cache configuration
        lines.append(f"\tcache {{")
        lines.append(f"\t\tttl {cache_ttl}s")
        lines.append(f"\t\tstale {cache_stale}s")
        lines.append(f"\t\tmax_size {cache_max_size}")
        lines.append(f"\t}}")
        lines.append("")

        # Reverse proxy to blob storage
        lines.append(f"\treverse_proxy {backend} {{")
        lines.append(f"\t\theader_up Host {{http.reverse_proxy.upstream.hostport}}")
        lines.append(f"\t\theader_up X-Forwarded-Host {{host}}")
        # Remove Azure-specific headers from response
        lines.append(f"\t\theader_down -x-ms-request-id")
        lines.append(f"\t\theader_down -x-ms-version")
        lines.append(f"\t\theader_down -x-ms-lease-status")
        lines.append(f"\t\theader_down -x-ms-blob-type")
        lines.append(f"\t}}")

        # Custom response headers
        if headers:
            lines.append("")
            lines.append(f"\theader {{")
            for key, value in headers.items():
                lines.append(f'\t\t{key} "{value}"')
            # Always add server identifier
            lines.append(f'\t\t-Server')
            lines.append(f"\t}}")

        # Logging
        lines.append("")
        lines.append(f"\tlog {{")
        lines.append(f"\t\toutput file /var/log/caddy/{domain}.log {{")
        lines.append(f"\t\t\troll_size 10MB")
        lines.append(f"\t\t\troll_keep 5")
        lines.append(f"\t\t}}")
        lines.append(f"\t}}")

        # Error handling — serve a simple error page
        lines.append("")
        lines.append(f"\thandle_errors {{")
        lines.append(f'\t\trespond "{{err.status_code}} {{err.status_text}}" {{err.status_code}}')
        lines.append(f"\t}}")

        lines.append("}")
        lines.append("")

    caddyfile_content = "\n".join(lines)

    output = Path(output_path)
    output.write_text(caddyfile_content)
    print(f"Generated {output_path} with {len(sites)} site(s)")


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "Caddyfile"
    generate_caddyfile(config_path, output_path)
