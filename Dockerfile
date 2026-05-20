FROM python:3.12-slim

# Don't write .pyc, flush stdout so logs appear in `docker logs` immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy metadata first so dependency installation can be cached when
# only application source changes.
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

# Data lives outside the image so the volume can be mounted from the
# host. Set the env var here so `finance` Just Works inside the
# container.
ENV FINANCE_DATABASE_PATH=/data/finance.db
RUN mkdir -p /data
VOLUME ["/data"]

ENTRYPOINT ["finance"]
CMD ["--help"]
