#!/bin/sh
set -e

CONFIG_PATH="${CONFIG_PATH:-/etc/blobfront/config.yaml}"
CADDYFILE_PATH="/etc/caddy/Caddyfile"

echo "BlobFront starting..."
echo "Config: ${CONFIG_PATH}"

# Generate Caddyfile from config
python3 /opt/blobfront/scripts/generate_caddyfile.py "${CONFIG_PATH}" "${CADDYFILE_PATH}"

# Create log directory
mkdir -p /var/log/caddy

# Validate Caddyfile
echo "Validating Caddyfile..."
caddy validate --config "${CADDYFILE_PATH}"

# Start Caddy
echo "Starting Caddy..."
exec caddy run --config "${CADDYFILE_PATH}"
