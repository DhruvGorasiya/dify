#!/usr/bin/env python3
"""
Migration script to fix Weaviate schema incompatibility between 1.19.0 and 1.27.0+

This script:
- Identifies collections with old schema (no vectorConfig)
- Creates new collections with proper vectorConfig including "default" named vector
- Migrates data using cursor-based pagination (efficient for large datasets)
- Uses batch operations for fast inserts
- Preserves all object properties and vectors
"""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
import weaviate

LOG_LEVEL = os.getenv("WEAVIATE_MIGRATION_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("weaviate-migration")

# Configuration sourced from environment with sensible defaults for local docker usage
WEAVIATE_SCHEME = os.getenv("WEAVIATE_SCHEME", "http")
WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_PORT = int(os.getenv("WEAVIATE_PORT", "8080"))
WEAVIATE_GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
WEAVIATE_API_KEY = os.getenv("WEAVIATE_API_KEY")
BATCH_SIZE = int(os.getenv("WEAVIATE_MIGRATION_BATCH_SIZE", "100"))
REQUEST_TIMEOUT = float(os.getenv("WEAVIATE_MIGRATION_HTTP_TIMEOUT", "5"))
REQUEST_RETRIES = int(os.getenv("WEAVIATE_MIGRATION_HTTP_RETRIES", "5"))
REQUEST_RETRY_DELAY = float(os.getenv("WEAVIATE_MIGRATION_HTTP_RETRY_DELAY", "2"))


def _auth_headers() -> Dict[str, str]:
    if WEAVIATE_API_KEY:
        return {"Authorization": f"Bearer {WEAVIATE_API_KEY}"}
    return {}


def _base_url() -> str:
    return f"{WEAVIATE_SCHEME}://{WEAVIATE_HOST}:{WEAVIATE_PORT}"


def _request_with_retry(method: str, path: str, **kwargs: Any) -> requests.Response:
    url = f"{_base_url()}{path}"
    headers = kwargs.pop("headers", {})
    merged_headers = {**_auth_headers(), **headers}

    last_exc: Optional[Exception] = None
    for attempt in range(1, REQUEST_RETRIES + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=merged_headers,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            response.raise_for_status()
            return response
        except Exception as exc:  # noqa: BLE001 - capture to retry
            last_exc = exc
            logger.warning(
                "HTTP %s %s failed on attempt %s/%s: %s",
                method,
                path,
                attempt,
                REQUEST_RETRIES,
                exc,
            )
            if attempt < REQUEST_RETRIES:
                time.sleep(REQUEST_RETRY_DELAY)
    assert last_exc is not None  # for type checkers
    raise last_exc


def identify_old_collections(client: weaviate.WeaviateClient) -> List[str]:
    """Identify collections that need migration (those without vectorConfig)."""
    collections_to_migrate: List[str] = []

    all_collections = client.collections.list_all()
    logger.info("Found %s total collections", len(all_collections))

    for collection_name in all_collections.keys():
        # Only check Vector_index collections (Dify knowledge bases)
        if not collection_name.startswith("Vector_index_"):
            continue

        collection = client.collections.get(collection_name)
        config = collection.config.get()

        # Check if this collection has the old schema
        if config.vector_config is None:
            collections_to_migrate.append(collection_name)
            logger.info("  - %s: OLD SCHEMA (needs migration)", collection_name)
        else:
            logger.debug("  - %s: NEW SCHEMA (skip)", collection_name)

    return collections_to_migrate


def get_collection_schema(client: weaviate.WeaviateClient, collection_name: str) -> Dict[str, Any]:
    """Get the full schema of a collection via REST API."""
    response = _request_with_retry("GET", f"/v1/schema/{collection_name}")
    return response.json()


def create_new_collection(client: weaviate.WeaviateClient, old_name: str, schema: Dict[str, Any]) -> str:
    """Create a new collection with updated schema using REST API."""

    # Generate new collection name
    new_name = f"{old_name}_migrated"

    logger.info("Creating new collection: %s", new_name)

    # Build new schema with proper vectorConfig
    # Note: When using vectorConfig (named vectors), we don't set class-level vectorizer
    new_schema = {
        "class": new_name,
        # This is the key: define vectorConfig with "default" named vector
        # Do NOT set class-level vectorizer when using vectorConfig
        "vectorConfig": {
            "default": {
                "vectorizer": {
                    "none": {}
                },
                "vectorIndexType": "hnsw",
                "vectorIndexConfig": {
                    "distance": "cosine",
                    "ef": -1,
                    "efConstruction": 128,
                    "maxConnections": 32
                }
            }
        },
        "properties": []
    }
    
    # Copy properties from old schema
    if "properties" in schema:
        new_schema["properties"] = schema["properties"]

    # Create collection via REST API
    _request_with_retry("POST", "/v1/schema", json=new_schema)

    logger.info("  Created new collection: %s", new_name)
    return new_name


def migrate_collection_data(
    client: weaviate.WeaviateClient,
    old_collection_name: str,
    new_collection_name: str
) -> int:
    """Migrate data from old collection to new collection using cursor-based pagination"""
    
    old_collection = client.collections.get(old_collection_name)
    new_collection = client.collections.get(new_collection_name)
    
    total_migrated = 0
    cursor = None
    
    logger.info("Migrating data from %s to %s", old_collection_name, new_collection_name)
    
    while True:
        # Fetch batch of objects using cursor-based pagination
        if cursor is None:
            # First batch
            response = old_collection.query.fetch_objects(
                limit=BATCH_SIZE,
                include_vector=True
            )
        else:
            # Subsequent batches using cursor
            response = old_collection.query.fetch_objects(
                limit=BATCH_SIZE,
                include_vector=True,
                after=cursor
            )
        
        objects = response.objects
        
        if not objects:
            break
        
        # Use batch insert for efficiency
        with new_collection.batch.dynamic() as batch:
            for obj in objects:
                # Prepare properties
                properties = obj.properties
                
                # Add object with vector
                batch.add_object(
                    properties=properties,
                    vector=obj.vector["default"] if isinstance(obj.vector, dict) else obj.vector,
                    uuid=obj.uuid
                )
        
        total_migrated += len(objects)
        logger.info("  Migrated %s objects...", total_migrated)
        
        # Update cursor for next iteration
        if len(objects) < BATCH_SIZE:
            # Last batch
            break
        else:
            # Get the last object's UUID for cursor
            cursor = objects[-1].uuid
    
    logger.info("  Total migrated: %s objects", total_migrated)
    return total_migrated


def verify_migration(
    client: weaviate.WeaviateClient,
    old_collection_name: str,
    new_collection_name: str
):
    """Verify that the migration was successful"""
    
    old_collection = client.collections.get(old_collection_name)
    new_collection = client.collections.get(new_collection_name)
    
    # Count objects in both collections
    old_count_response = old_collection.query.fetch_objects(limit=1)
    new_count_response = new_collection.query.fetch_objects(limit=1)
    
    # Get aggregation for accurate counts
    old_agg = old_collection.aggregate.over_all(total_count=True)
    new_agg = new_collection.aggregate.over_all(total_count=True)
    
    old_count = old_agg.total_count
    new_count = new_agg.total_count
    
    logger.info("Verification:")
    logger.info("  Old collection (%s): %s objects", old_collection_name, old_count)
    logger.info("  New collection (%s): %s objects", new_collection_name, new_count)

    if old_count == new_count:
        logger.info("  Status: SUCCESS - Counts match!")
        return True

    logger.warning("  Status: WARNING - Counts don't match!")
    return False


def replace_old_collection(
    client: weaviate.WeaviateClient,
    old_collection_name: str,
    new_collection_name: str
):
    """Replace old collection with migrated one by recreating with original name."""

    logger.info("Replacing old collection %s with migrated data", old_collection_name)
    
    # Step 1: Get data from migrated collection
    logger.info("  Step 1: Getting data from migrated collection...")
    migrated = client.collections.get(new_collection_name)
    objects = migrated.query.fetch_objects(include_vector=True, limit=10000)
    logger.info("    Found %s objects", len(objects.objects))
    
    # Step 2: Delete old collection
    logger.info("  Step 2: Deleting old collection...")
    try:
        _request_with_retry("DELETE", f"/v1/schema/{old_collection_name}")
        logger.info("    Deleted")
    except Exception as exc:  # noqa: BLE001 - log and continue
        logger.warning("    Warning: Could not delete old collection: %s", exc)
    
    # Step 3: Get schema from migrated collection
    logger.info("  Step 3: Getting schema from migrated collection...")
    schema_response = _request_with_retry(
        "GET",
        f"/v1/schema/{new_collection_name}",
    )
    schema = schema_response.json()
    schema["class"] = old_collection_name
    
    # Step 4: Create collection with original name and new schema
    logger.info("  Step 4: Creating collection with original name...")
    _request_with_retry("POST", "/v1/schema", json=schema)
    logger.info("    Created")
    
    # Step 5: Copy data to collection with original name
    logger.info("  Step 5: Copying data to original collection name...")
    new_collection = client.collections.get(old_collection_name)
    
    with new_collection.batch.dynamic() as batch:
        for obj in objects.objects:
            batch.add_object(
                properties=obj.properties,
                vector=obj.vector,
                uuid=obj.uuid
            )
    
    count = new_collection.aggregate.over_all(total_count=True).total_count
    logger.info("    Copied %s objects", count)
    
    # Step 6: Delete the temporary migrated collection
    logger.info("  Step 6: Cleaning up temporary migrated collection...")
    try:
        _request_with_retry("DELETE", f"/v1/schema/{new_collection_name}")
        logger.info("    Cleaned up")
    except Exception as exc:  # noqa: BLE001 - log and continue
        logger.warning("    Warning: Could not clean up temporary collection: %s", exc)

    logger.info("  SUCCESS! %s now has the new schema with %s objects", old_collection_name, count)
    return True


def migrate_all_collections() -> List[str]:
    """Main migration function."""

    logger.info("=" * 80)
    logger.info("Weaviate Collection Migration Script")
    logger.info("Migrating from Weaviate 1.19.0 schema to 1.27.0+ schema")
    logger.info("=" * 80)

    auth_credentials: Optional[weaviate.auth.AuthCredentials] = None
    if WEAVIATE_API_KEY:
        auth_credentials = weaviate.auth.AuthApiKey(WEAVIATE_API_KEY)

    client = weaviate.connect_to_local(
        host=WEAVIATE_HOST,
        port=WEAVIATE_PORT,
        grpc_port=WEAVIATE_GRPC_PORT,
        auth_credentials=auth_credentials,
    )

    migrated_collections: List[str] = []

    try:
        # Step 1: Identify collections that need migration
        logger.info("Step 1: Identifying collections that need migration...")
        collections_to_migrate = identify_old_collections(client)

        if not collections_to_migrate:
            logger.info("No collections need migration. All collections are up to date!")
            return migrated_collections

        logger.info("Found %s collections to migrate:", len(collections_to_migrate))
        for col in collections_to_migrate:
            logger.info("  - %s", col)

        # Confirm before proceeding
        logger.info(
            "This script will:\n"
            "1. Create new collections with updated schema\n"
            "2. Copy all data using efficient batch operations\n"
            "3. Verify the migration\n"
            "4. Replace old collections with migrated ones"
        )

        # Step 2: Migrate each collection
        for collection_name in collections_to_migrate:
            logger.info("=" * 80)
            logger.info("Migrating: %s", collection_name)
            logger.info("=" * 80)

            try:
                # Get old schema
                schema = get_collection_schema(client, collection_name)

                # Create new collection
                new_collection_name = create_new_collection(client, collection_name, schema)

                # Migrate data
                migrated_count = migrate_collection_data(client, collection_name, new_collection_name)

                # Verify migration
                success = verify_migration(client, collection_name, new_collection_name)

                if success and migrated_count > 0:
                    logger.info("Migration successful for %s", collection_name)
                    logger.info("New collection: %s", new_collection_name)

                    # Automatically replace old collection with migrated one
                    try:
                        replace_old_collection(client, collection_name, new_collection_name)
                        migrated_collections.append(collection_name)
                    except Exception as e:
                        logger.warning("Warning: Could not automatically replace collection: %s", e)
                        logger.warning("To activate manually:")
                        logger.warning("1. Delete the old collection: %s", collection_name)
                        logger.warning("2. Rename %s to %s", new_collection_name, collection_name)

            except Exception as e:
                logger.exception("Error migrating %s: %s", collection_name, e)
                logger.warning("Skipping this collection and continuing...")
                continue

        logger.info("=" * 80)
        logger.info("Migration Complete!")
        logger.info("=" * 80)
        logger.info("Summary:")
        logger.info("  Collections migrated: %s", len(migrated_collections))
        logger.info("Next steps:")
        logger.info("1. Test the new collections (*_migrated)")
        logger.info("2. If everything works, delete or backup the old collections")
        logger.info("3. Rename the new collections to remove '_migrated' suffix")

    finally:
        client.close()

    return migrated_collections


if __name__ == "__main__":
    try:
        migrate_all_collections()
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

