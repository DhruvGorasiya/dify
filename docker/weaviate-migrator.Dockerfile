FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime dependencies
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

ARG WEAVIATE_CLIENT_VERSION=4.17.0
ARG REQUESTS_VERSION=2.32.3

RUN pip install \
        "weaviate-client==${WEAVIATE_CLIENT_VERSION}" \
        "requests==${REQUESTS_VERSION}"

COPY migrate_weaviate_collections.py /app/migrate_weaviate_collections.py
COPY auto_migrate_weaviate.py /app/auto_migrate_weaviate.py

ENTRYPOINT ["python", "/app/auto_migrate_weaviate.py"]

