# ProxyHealth AI API image (ARCHITECTURE §5.3). Build from the repo root:
#   docker build -t proxyhealth-api apps/api
# Run (mock mode, zero keys):
#   docker run --rm -p 8080:8080 -e AI_PROVIDER=mock proxyhealth-api
# Real keys come from the host's secret manager as env vars (GEMINI_KEYS, INSTALL_HASH_SECRET,
# ADMIN_TOKEN); never bake them into the image. Not built locally in Phase 1 (no Docker here);
# CI builds it (WP8).
FROM python:3.13-slim

# TRUSTED_PROXY_HOPS=1: the host's front end (Cloud Run, Fly.io) appends the real client address
# to X-Forwarded-For and the per-IP-class rate limit reads that entry, not the proxy's socket
# address (with 0 every user would share one bucket) and not the client-supplied entries left of
# it (spoofable). Set 2 behind an extra external HTTPS load balancer; 0 if uvicorn is reachable
# directly (uvicorn's own --forwarded-allow-ips='*' would trust the spoofable leftmost entry).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    VAR_DIR=/app/var \
    TRUSTED_PROXY_HOPS=1

WORKDIR /app

# Runtime pins only: everything above the "dev only" marker in requirements.txt.
COPY requirements.txt /tmp/requirements.txt
RUN sed '/^# --- dev only/,$d' /tmp/requirements.txt > /tmp/runtime.txt \
    && pip install --no-cache-dir -r /tmp/runtime.txt \
    && rm /tmp/requirements.txt /tmp/runtime.txt

# Code and vetted data only: no tests, no .env, no var/ state from the build machine.
COPY proxyhealth_api/ /app/proxyhealth_api/
COPY data/ /app/data/

# Non-root; var/ holds only keypool.json, langpacks/ and feedback_counts.sqlite (no user content).
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/var \
    && chown -R app:app /app/var
USER app

EXPOSE 8080

# One worker (the key pool and rate limits are in-process state); 32 concurrent requests; the
# host's request timeout is 120 s (Cloud Run). uvicorn's access log stays off (content-free
# JSON logging comes from proxyhealth_api.logging_).
CMD ["sh", "-c", "exec uvicorn proxyhealth_api.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --limit-concurrency 32 --timeout-keep-alive 5 --no-access-log"]
