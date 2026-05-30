"""Unit tests for scripts/generate_caddyfile.py.

These assert the structure of the generated Caddyfile without needing a Caddy
binary. End-to-end validation (that Caddy actually accepts the output) is done
in CI by building the image and running `caddy validate` — see
.github/workflows/ci.yml.
"""

import sys
from pathlib import Path

import pytest

# The generator lives in scripts/ and is imported as a plain module.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import generate_caddyfile  # noqa: E402


BASIC = """
global:
  email: admin@example.com
sites:
  - domain: example.com
    backend: https://acct.z6.web.core.windows.net
"""


def generate(tmp_path, config_text):
    """Write config_text to a temp config, run the generator, return the output."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text(config_text)
    out = tmp_path / "Caddyfile"
    generate_caddyfile.generate_caddyfile(str(cfg), str(out))
    return out.read_text()


# --- error handling ---------------------------------------------------------

def test_missing_config_exits_nonzero(tmp_path):
    with pytest.raises(SystemExit) as exc:
        generate_caddyfile.generate_caddyfile(
            str(tmp_path / "does-not-exist.yaml"), str(tmp_path / "out")
        )
    assert exc.value.code == 1


def test_empty_sites_exits_nonzero(tmp_path):
    with pytest.raises(SystemExit) as exc:
        generate(tmp_path, "global:\n  email: a@b.com\nsites: []\n")
    assert exc.value.code == 1


# --- global options block ---------------------------------------------------

def test_global_block_has_email_and_cache_order(tmp_path):
    out = generate(tmp_path, BASIC)
    assert "email admin@example.com" in out
    # The `order cache before rewrite` line is what activates the cache-handler.
    assert "order cache before rewrite" in out


# --- reverse proxy / header rewriting ---------------------------------------

def test_reverse_proxy_and_host_rewrite(tmp_path):
    out = generate(tmp_path, BASIC)
    assert "reverse_proxy https://acct.z6.web.core.windows.net {" in out
    assert "header_up Host {http.reverse_proxy.upstream.hostport}" in out
    assert "header_up X-Forwarded-Host {host}" in out


def test_azure_response_headers_stripped(tmp_path):
    out = generate(tmp_path, BASIC)
    for header in (
        "-x-ms-request-id",
        "-x-ms-version",
        "-x-ms-lease-status",
        "-x-ms-blob-type",
    ):
        assert f"header_down {header}" in out


def test_backend_trailing_slash_stripped(tmp_path):
    out = generate(
        tmp_path,
        """
global:
  email: a@b.com
sites:
  - domain: example.com
    backend: https://acct.z6.web.core.windows.net/
""",
    )
    assert "reverse_proxy https://acct.z6.web.core.windows.net {" in out
    assert "windows.net/ {" not in out


# --- caching ----------------------------------------------------------------

def test_cache_ttls_default_when_unset(tmp_path):
    out = generate(tmp_path, BASIC)
    assert "ttl 3600s" in out
    assert "stale 86400s" in out


def test_global_cache_defaults_inherited(tmp_path):
    out = generate(
        tmp_path,
        """
global:
  email: a@b.com
  cache_ttl: 60
  cache_stale: 120
sites:
  - domain: example.com
    backend: https://acct.z6.web.core.windows.net
""",
    )
    assert "ttl 60s" in out
    assert "stale 120s" in out


def test_per_site_cache_overrides_global(tmp_path):
    out = generate(
        tmp_path,
        """
global:
  email: a@b.com
  cache_ttl: 60
sites:
  - domain: example.com
    backend: https://acct.z6.web.core.windows.net
    cache_ttl: 999
""",
    )
    assert "ttl 999s" in out
    assert "ttl 60s" not in out


# --- custom headers ---------------------------------------------------------

def test_custom_headers_block_and_server_strip(tmp_path):
    out = generate(
        tmp_path,
        """
global:
  email: a@b.com
sites:
  - domain: example.com
    backend: https://acct.z6.web.core.windows.net
    headers:
      X-Frame-Options: DENY
""",
    )
    assert 'X-Frame-Options "DENY"' in out
    # Server is only stripped inside the optional custom-header block.
    assert "-Server" in out


def test_no_header_block_without_custom_headers(tmp_path):
    out = generate(tmp_path, BASIC)
    assert "-Server" not in out


# --- www redirect -----------------------------------------------------------

def test_www_redirect_emitted_when_enabled(tmp_path):
    out = generate(tmp_path, BASIC + "    redirect_www: true\n")
    assert "www.example.com {" in out
    assert "redir https://example.com{uri} permanent" in out


def test_no_www_redirect_by_default(tmp_path):
    out = generate(tmp_path, BASIC)
    assert "www.example.com" not in out


# --- multiple sites ---------------------------------------------------------

def test_multiple_site_blocks(tmp_path):
    out = generate(
        tmp_path,
        """
global:
  email: a@b.com
sites:
  - domain: one.com
    backend: https://one.z6.web.core.windows.net
  - domain: two.com
    backend: https://two.z6.web.core.windows.net
""",
    )
    assert "one.com {" in out
    assert "two.com {" in out
