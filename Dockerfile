# Stage 1: Build Caddy with cache plugin
FROM caddy:2-builder AS builder

RUN xcaddy build \
    --with github.com/caddyserver/cache-handler

# Stage 2: Runtime
FROM python:3.12-slim

# Install minimal dependencies
RUN pip install --no-cache-dir pyyaml

# Copy custom Caddy binary
COPY --from=builder /usr/bin/caddy /usr/bin/caddy

# Copy application files
COPY scripts/ /opt/blobfront/scripts/
COPY config.yaml /etc/blobfront/config.yaml

RUN chmod +x /opt/blobfront/scripts/entrypoint.sh

# Caddy ports
EXPOSE 80 443

# Caddy data & config volumes
VOLUME /data
VOLUME /config

ENTRYPOINT ["/opt/blobfront/scripts/entrypoint.sh"]
