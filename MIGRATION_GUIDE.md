# Weaviate 1.19.0 to 1.33.1 Migration Guide for Dify

This guide helps you migrate your Dify knowledge bases from Weaviate 1.19.0 to Weaviate 1.33.1 while preserving all embeddings.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ with virtual environment support
- Access to both old and new Dify versions

## Overview

The migration process:
1. Backup data from Weaviate 1.19.0 (old schema)
2. Upgrade to Weaviate 1.33.1
3. Restore backup (preserves old schema)
4. Run migration script to fix schema
5. Verify in Dify UI

---

## Step 1: Prepare on OLD Dify Version (Weaviate 1.19.0)

### 1.1 Checkout old version
```bash
cd /Users/dhruvgorasiya/Documents/Weaviate/Integrations/dify
git checkout 0b35bc1ede  # Or your specific old commit/branch
```

### 1.2 Add backup module to docker-compose.yaml

Edit `docker/docker-compose.yaml` and find the `weaviate:` service. Add these lines:

```yaml
  weaviate:
    image: semitechnologies/weaviate:1.19.0
    volumes:
      - ./volumes/weaviate:/var/lib/weaviate
      - ./volumes/weaviate_backups:/var/lib/weaviate/backups  # ADD THIS
    ports:
      - "8080:8080"      # ADD THIS
      - "50051:50051"    # ADD THIS
    environment:
      ENABLE_MODULES: backup-filesystem                       # ADD THIS
      BACKUP_FILESYSTEM_PATH: /var/lib/weaviate/backups      # ADD THIS
      # ... rest of environment variables
```

### 1.3 Clean and start fresh
```bash
cd docker
docker compose down
rm -rf volumes/*
docker compose --profile weaviate up -d
```

### 1.4 Upload documents in Dify UI

1. Go to http://localhost
2. Create a knowledge base
3. Upload your documents
4. **IMPORTANT**: Choose "High Quality" indexing (not "Economy")
5. Wait for processing to complete (status shows "Completed")

---

## Step 2: Backup Data from Weaviate 1.19.0

### 2.1 Wait for Weaviate to be ready
```bash
sleep 10
```

### 2.2 Find your collection names
```bash
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/schema" | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
collections = [cls['class'] for cls in data.get('classes', []) if 'Vector_index' in cls['class']]
print('Collections to backup:')
for col in collections:
    print(f'  - {col}')
"
```

### 2.3 Create backup for each collection

Replace `COLLECTION_NAME` with your actual collection name from step 2.2:

```bash
curl -X POST \
  -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/backups/filesystem" \
  -d '{
  "id": "dify-backup-v1-19",
  "include": ["COLLECTION_NAME"]
}'
```

For multiple collections, you can include all at once:
```bash
curl -X POST \
  -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/backups/filesystem" \
  -d '{
  "id": "dify-backup-v1-19",
  "include": ["Collection1_Node", "Collection2_Node", "Collection3_Node"]
}'
```

### 2.4 Verify backup completed
```bash
sleep 5
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/backups/filesystem/dify-backup-v1-19" | \
  python3 -m json.tool | grep status
```

Should show: `"status": "SUCCESS"`

### 2.5 Verify backup files exist
```bash
ls -lh docker/volumes/weaviate_backups/dify-backup-v1-19/
```

You should see `backup_config.json` and a `node1/` directory.

---

## Step 3: Upgrade to Weaviate 1.33.1

### 3.1 Stash your docker-compose changes
```bash
cd /Users/dhruvgorasiya/Documents/Weaviate/Integrations/dify
git stash push -m "Added backup module and ports" docker/docker-compose.yaml
```

### 3.2 Checkout new version
```bash
git checkout weaviate-1.27  # Or main branch
```

### 3.3 Add backup volume mount to new docker-compose.yaml

Edit `docker/docker-compose.yaml` in the new version and find the `weaviate:` service. 

The backup module should already be there, but add the backup volume:

```yaml
  weaviate:
    image: semitechnologies/weaviate:1.33.1
    volumes:
      - ./volumes/weaviate:/var/lib/weaviate
      - ./volumes/weaviate_backups:/var/lib/weaviate/backups  # ADD THIS IF NOT PRESENT
    environment:
      ENABLE_MODULES: backup-filesystem        # Should already be there
      BACKUP_FILESYSTEM_PATH: /var/lib/weaviate/backups  # Should already be there
```

### 3.4 Clean Weaviate data (but keep backup) and start
```bash
cd docker
docker compose down
rm -rf volumes/weaviate/*    # Delete Weaviate data
# DO NOT delete volumes/weaviate_backups/  ← Keep this!
docker compose --profile weaviate up -d
```

---

## Step 4: Restore Backup on Weaviate 1.33.1

### 4.1 Wait for Weaviate to start
```bash
sleep 10
```

### 4.2 Restore the backup
```bash
curl -X POST \
  -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/backups/filesystem/dify-backup-v1-19/restore" \
  -d '{}'
```

### 4.3 Check restore status
```bash
sleep 5
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/backups/filesystem/dify-backup-v1-19/restore" | \
  python3 -m json.tool | grep status
```

Should show: `"status": "SUCCESS"`

---

## Step 5: Run Migration Script to Fix Schema

### 5.1 Create Python virtual environment (if not already done)
```bash
cd /Users/dhruvgorasiya/Documents/Weaviate/Integrations/dify
python3 -m venv weaviate_migration_env
source weaviate_migration_env/bin/activate
pip install weaviate-client requests
```

### 5.2 Run the migration script
```bash
python migrate_weaviate_collections.py
```

The script will:
- Identify collections with old schema (no vectorConfig)
- Create new collections with proper vectorConfig and "default" named vector
- Copy all data including vectors using cursor-based pagination
- Replace old collections with migrated ones automatically
- Clean up temporary collections

Expected output:
```
================================================================================
Weaviate Collection Migration Script
Migrating from Weaviate 1.19.0 schema to 1.27.0+ schema
================================================================================

Step 1: Identifying collections that need migration...
Found X total collections
  - Vector_index_XXX_Node: OLD SCHEMA (needs migration)

Found 1 collections to migrate:
  - Vector_index_XXX_Node

...

Replacing old collection with migrated data...
  Step 1: Getting data from migrated collection...
    Found X objects
  Step 2: Deleting old collection...
    Deleted
  Step 3: Getting schema from migrated collection...
  Step 4: Creating collection with original name...
    Created
  Step 5: Copying data to original collection name...
    Copied X objects
  Step 6: Cleaning up temporary migrated collection...
    Cleaned up

  SUCCESS! Vector_index_XXX_Node now has the new schema with X objects

Migration Complete!
```

---

## Step 6: Restart Dify Services

```bash
cd docker
docker compose restart api worker worker_beat
```

Wait a few seconds for services to restart.

---

## Step 7: Verify in Dify UI

1. Go to http://localhost
2. Open your knowledge base
3. Go to "Retrieval Testing"
4. Search for keywords from your documents
5. **It should now work without errors!**

---

## Cleanup (Optional)

After verifying everything works, you can:

### Delete backup files
```bash
rm -rf docker/volumes/weaviate_backups/
```

### Delete temporary files
```bash
rm -rf weaviate_migration_env/
rm weaviate_backup.json  # If you created a JSON export earlier
rm weaviate_data_export.json
```

---

## Troubleshooting

### Backup module not available in 1.19.0
The `backup-filesystem` module might not be available in Weaviate 1.19.0. In that case, use JSON export:

```bash
# Export all data to JSON
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/objects?class=COLLECTION_NAME&include=vector&limit=10000" \
  > weaviate_backup.json
```

Then manually import using a modified migration script.

### Ports not accessible
Make sure ports 8080 and 50051 are exposed in docker-compose.yaml

### Collections still show old schema after restore
This is expected! The restore preserves the old schema. The migration script is required to fix it.

---

## Summary

**What you need:**
1. `docker-compose.yaml` with backup module enabled (both versions)
2. `migrate_weaviate_collections.py` script
3. Backup created on Weaviate 1.19.0
4. Migration script run on Weaviate 1.33.1

**What gets preserved:**
- All document text and metadata
- All vector embeddings (no need to regenerate!)
- All UUIDs and relationships

**What changes:**
- Schema format (old: `vectorizer: none`, new: `vectorConfig: {default: {...}}`)
- Weaviate version (1.19.0 → 1.33.1)
- Dify weaviate-client (v3 → v4)

