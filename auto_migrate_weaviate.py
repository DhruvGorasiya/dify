#!/usr/bin/env python3
"""
Utility entrypoint that waits for Weaviate to become available and
triggers the schema migration when legacy 1.19-style collections are present.
"""

from __future__ import annotations

import os
import socket
import sys
import time
from typing import Optional

import requests

from migrate_weaviate_collections import (
    REQUEST_TIMEOUT,
    WEAVIATE_API_KEY,
    WEAVIATE_HOST,
    WEAVIATE_PORT,
    WEAVIATE_SCHEME,
    logger as migration_logger,
    migrate_all_collections,
)


def _auth_headers() -> dict[str, str]:
    if WEAVIATE_API_KEY:
        return {"Authorization": f"Bearer {WEAVIATE_API_KEY}"}
    return {}


def _base_url() -> str:
    return f"{WEAVIATE_SCHEME}://{WEAVIATE_HOST}:{WEAVIATE_PORT}"


WAIT_TIMEOUT_SECONDS = int(os.getenv("WEAVIATE_MIGRATION_WAIT_TIMEOUT", "600"))
WAIT_POLL_INTERVAL = float(os.getenv("WEAVIATE_MIGRATION_WAIT_INTERVAL", "5"))
CHECK_HEALTH_PATH = os.getenv("WEAVIATE_MIGRATION_HEALTH_PATH", "/v1/meta")
AUTO_MIGRATE_ENABLED = os.getenv("WEAVIATE_AUTO_MIGRATE", "true").lower() in {"1", "true", "yes"}
IGNORE_UNRESOLVED_HOST = os.getenv("WEAVIATE_MIGRATION_IGNORE_UNRESOLVED_HOST", "true").lower() in {
    "1",
    "true",
    "yes",
}


def wait_for_weaviate() -> Optional[dict]:
    """Wait until Weaviate responds successfully with health/meta information."""
    migration_logger.info(
        "Waiting for Weaviate at %s (timeout: %ss)",
        _base_url(),
        WAIT_TIMEOUT_SECONDS,
    )

    start_time = time.time()
    attempts = 0
    last_error: Optional[Exception] = None

    while time.time() - start_time < WAIT_TIMEOUT_SECONDS:
        attempts += 1
        try:
            response = requests.get(
                f"{_base_url()}{CHECK_HEALTH_PATH}",
                headers=_auth_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            version = payload.get("version", {}) or payload
            migration_logger.info(
                "Connected to Weaviate (version: %s, gitHash: %s)",
                version.get("version") or version.get("build"),
                version.get("gitHash"),
            )
            return payload
        except Exception as exc:  # noqa: BLE001 - we only log and retry here
            last_error = exc
            migration_logger.debug(
                "Weaviate not ready yet (attempt %s): %s", attempts, exc
            )
            time.sleep(WAIT_POLL_INTERVAL)

    migration_logger.error(
        "Timed out waiting for Weaviate after %ss: %s",
        WAIT_TIMEOUT_SECONDS,
        last_error,
    )
    return None


def main() -> int:
    if not AUTO_MIGRATE_ENABLED:
        migration_logger.info("WEAVIATE_AUTO_MIGRATE disabled; exiting without changes.")
        return 0

    if IGNORE_UNRESOLVED_HOST:
        try:
            socket.getaddrinfo(WEAVIATE_HOST, WEAVIATE_PORT)
        except socket.gaierror:
            migration_logger.info(
                "Weaviate host %s is not resolvable in this environment; skipping migration.",
                WEAVIATE_HOST,
            )
            return 0

    payload = wait_for_weaviate()
    if payload is None:
        return 1

    try:
        migrated_collections = migrate_all_collections()
    except Exception as exc:  # noqa: BLE001 - top-level error reporting
        migration_logger.exception("Weaviate migration failed: %s", exc)
        return 2

    if migrated_collections:
        migration_logger.info(
            "Migrated collections: %s", ", ".join(sorted(migrated_collections))
        )
    else:
        migration_logger.info("No legacy collections detected; nothing to migrate.")

    migration_logger.info("Weaviate migration task completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

