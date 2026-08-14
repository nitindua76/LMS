FROM python:3.12-slim

# Build-time only proxy config — deliberately ARG, not ENV. ENV would persist
# into the running container, and at runtime this service talks to db/redis/
# minio/livekit/etc. by their compose service names, which a corporate proxy
# can't resolve. Values come from docker-compose.yml's build.args (empty/unset
# when there's no proxy, e.g. in CI), so nothing is baked into the image layers
# beyond this build.
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# apt-get does not reliably honor the HTTP_PROXY/HTTPS_PROXY env vars (its own
# HTTP transport only reads Acquire::http(s)::Proxy, or the lowercase
# http_proxy/https_proxy inconsistently) — without this it silently ignores
# the proxy and hangs retrying each Debian mirror directly for minutes.
RUN if [ -n "$HTTP_PROXY" ]; then echo "Acquire::http::Proxy \"$HTTP_PROXY\";" > /etc/apt/apt.conf.d/01proxy; fi && \
    if [ -n "$HTTPS_PROXY" ]; then echo "Acquire::https::Proxy \"$HTTPS_PROXY\";" >> /etc/apt/apt.conf.d/01proxy; fi

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
