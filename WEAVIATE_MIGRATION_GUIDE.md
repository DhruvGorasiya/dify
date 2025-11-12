# Weaviate 1.19 to 1.27+ Migration Guide for Dify

Complete guide to safely migrate Dify knowledge bases from Weaviate 1.19 to 1.27/1.33.

---

## Choose Your Path

### Automatic Migration (Recommended for new upgrades)

When you run `docker compose --profile weaviate up`, Dify now starts an init container named `weaviate-migrator`. This job waits for the Weaviate service to become healthy and then executes the `migrate_weaviate_collections.py` script automatically. Existing 1.19-style collections are migrated in-place before the API and worker services begin accepting traffic.

Key environment variables (set them in `docker/.env` if you need to customise the behaviour):

- `WEAVIATE_AUTO_MIGRATE` (default `true`): disable to skip the automatic job.
- `WEAVIATE_MIGRATION_WAIT_TIMEOUT` (default `600` seconds): total time to wait for Weaviate to become ready.
- `WEAVIATE_MIGRATION_WAIT_INTERVAL` (default `5` seconds): poll interval while waiting.
- `WEAVIATE_MIGRATION_IGNORE_UNRESOLVED_HOST` (default `true`): allows the job to exit successfully when the `weaviate` service is not part of the compose deployment (for example, if you are using a different vector store).

If you prefer to run the migration manually, set `WEAVIATE_AUTO_MIGRATE=false` and follow Path A or Path B below.

### Path A: Starting from Weaviate 1.19 (Recommended - With Backup)
**If you are currently on Weaviate 1.19 and planning to upgrade:**
- Backup data first (safest approach)
- Then upgrade and migrate
- **Go to:** [Path A - Migration with Backup](#path-a-migration-with-backup-from-1.19)

### Path B: Already on Weaviate 1.27+
**If you already upgraded to 1.27+ and have broken knowledge bases:**
- Can't backup from old version anymore
- Direct recovery possible
- **Go to:** [Path B - Direct Recovery](#path-b-direct-recovery-already-on-1.33)

---

## Path A: Migration with Backup (From 1.19)

### Prerequisites
- Currently running Weaviate 1.19
- Docker and Docker Compose
- Python 3.11+

---

### Step A1: Enable Backup Module on Weaviate 1.19

Edit `docker/docker-compose.yaml` and add backup configuration to the `weaviate` service:

```yaml
  weaviate:
    image: semitechnologies/weaviate:1.19.0
    volumes:
      - ./volumes/weaviate:/var/lib/weaviate
      - ./volumes/weaviate_backups:/var/lib/weaviate/backups  # ADD THIS
    ports:
      - "8080:8080"      # ADD THIS (if not present)
      - "50051:50051"    # ADD THIS (if not present)
    environment:
      ENABLE_MODULES: backup-filesystem                       # ADD THIS
      BACKUP_FILESYSTEM_PATH: /var/lib/weaviate/backups      # ADD THIS
      # ... rest of your environment variables
```

**Restart Weaviate to apply changes:**

```bash
cd docker
docker compose down && docker compose --profile up -d
sleep 10
```

---

### Step A2: Backup Data from Weaviate 1.19

#### A2.1 Find Your Collection Names

```bash
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/schema" | \
  python3 -c "
import json, sys
data = json.load(sys.stdin)
collections = [cls['class'] for cls in data.get('classes', [])]
print('Collections to backup:')
for col in collections:
    print(f'  - {col}')
"
```

#### A2.2 Create Backup

**For all collections at once:**

```bash
curl -X POST \
  -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/backups/filesystem" \
  -d '{
  "id": "kb-backup",
  "include": ["Vector_index_COLLECTION1_Node", "Vector_index_COLLECTION2_Node"]
}'
```

Replace `Vector_index_COLLECTION1_Node`, etc. with your actual collection names from A2.1.

**OR**

```bash
curl -X POST \
  -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/backups/filesystem" \
  -d '{
  "id": "kb-backup"
}'
```

#### A2.3 Verify Backup Completed

```bash
sleep 5
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/backups/filesystem/kb-backup" | \
  python3 -m json.tool | grep status
```

**Expected:** `"status": "SUCCESS"`

#### A2.4 Verify Backup Files Exist

```bash
ls -lh docker/volumes/weaviate_backups/kb-backup/
```

You should see backup files for your collections.

---

### Step A3: Upgrade to Weaviate 1.27+

#### A3.1 Upgrade to Latest Dify Version

```bash
cd /path/to/dify
git fetch origin
git checkout main  # or the specific version branch like v0.9.2This will automatically update `docker-compose.yaml` to use the newer Weaviate version (1.27+ or 1.33+).
```

**Verify the Weaviate version in docker-compose.yaml:**

```bash
grep "image: semitechnologies/weaviate" docker/docker-compose.yaml
```

# Should show: image: semitechnologies/weaviate:1.27.0

#### A3.2 Stop and Upgrade

```bash
cd docker
docker compose down
docker compose up -d
sleep 20  # Wait for Weaviate to start
```

### Step A4: Fix Orphaned LSM Data

```bash
cd volumes/weaviate

# Check for orphaned directories
ls -d vector_index_*_node_*_lsm 2>/dev/null

# If found, copy them to correct location
for dir in vector_index_*_node_*_lsm; do
  [ -d "$dir" ] || continue
  
  # Extract index ID and shard ID
  index_id=$(echo "$dir" | sed -n 's/vector_index_\([^_]*_[^_]*_[^_]*_[^_]*_[^_]*\)_node_.*/\1/p')
  shard_id=$(echo "$dir" | sed -n 's/.*_node_\([^_]*\)_lsm/\1/p')
  
  # Create target directory and copy
  mkdir -p "vector_index_${index_id}_node/$shard_id/lsm"
  cp -a "$dir/"* "vector_index_${index_id}_node/$shard_id/lsm/"
  
  echo "✓ Copied $dir"
done

cd path/to/docker
docker compose restart weaviate
sleep 15
```

---

### Step A5: Migrate Schema

#### A5.1 Install Dependencies

```bash
cd /path/to/dify
python3 -m venv weaviate_migration_env
source weaviate_migration_env/bin/activate
pip install weaviate-client requests
```

#### A5.2 Run Migration Script

```bash
python3 migrate_weaviate_collections.py
```

#### A5.3 Restart Dify Services

```bash
cd docker
docker compose restart api worker worker_beat
```

Wait 10-15 seconds for services to restart.

#### A5.4 Verify in Dify UI

1. Go to http://localhost
2. Open your knowledge bases
3. Try "Retrieval Testing"
4. **Should work without errors!** 

---

## Path B: Direct Recovery (Already on 1.27+)

### Prerequisites
- Already running Weaviate 1.27+ or 1.33+
- Knowledge bases are broken
- Docker and Docker Compose
- Python 3.11+

**Do NOT try to rollback to 1.19** - it will make things worse!

---

### Step B1: Fix Orphaned LSM Data

#### B1.1 Check for Orphaned Data

```bash
cd docker/volumes/weaviate
ls -d vector_index_*_node_*_lsm 2>/dev/null
```

**If you see directories ending in `_lsm`, you have orphaned data.**

Example output:
```
vector_index_ABC123_node_SHARD456_lsm/
vector_index_XYZ789_node_SHARD999_lsm/
```

#### B1.2 Stop Weaviate

```bash
cd ../../docker
docker compose stop weaviate
```

#### B1.3 Copy Orphaned Data to Correct Location

```bash
cd volumes/weaviate

for dir in vector_index_*_node_*_lsm; do
  [ -d "$dir" ] || continue
  
  # Extract index ID and shard ID
  index_id=$(echo "$dir" | sed -n 's/vector_index_\([^_]*_[^_]*_[^_]*_[^_]*_[^_]*\)_node_.*/\1/p')
  shard_id=$(echo "$dir" | sed -n 's/.*_node_\([^_]*\)_lsm/\1/p')
  
  # Create target directory and copy
  mkdir -p "vector_index_${index_id}_node/$shard_id/lsm"
  cp -a "$dir/"* "vector_index_${index_id}_node/$shard_id/lsm/"
  
  echo "✓ Copied $dir"
done
```

#### B1.4 Restart Weaviate

```bash
cd ../../docker
docker compose start weaviate
sleep 15
```

#### B1.5 Verify Data is Accessible

```bash
# List collections
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/schema" | python3 -c "
import sys, json
for cls in json.load(sys.stdin).get('classes', []):
    if cls['class'].startswith('Vector_index_'):
        print(cls['class'])
"
```

**Check object count for each collection:**

```bash
# Replace YOUR_COLLECTION_NAME with actual name from above
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/objects?class=YOUR_COLLECTION_NAME&limit=0" | \
  python3 -c "import sys, json; print(f'Objects: {json.load(sys.stdin).get(\"totalResults\", 0)}')"
```

**Expected:** Should show your actual object count (not 0!)

**If objects appear:** Continue to Step B2  
**If still 0:** Check `docker compose logs weaviate` for errors

---

### Step B2: Migrate Schema

#### B2.1 Install Dependencies

```bash
cd /path/to/dify
python3 -m venv weaviate_migration_env
source weaviate_migration_env/bin/activate
pip install weaviate-client requests
```

#### B2.2 Run Migration Script

```bash
python3 migrate_weaviate_collections.py
```

#### B2.3 Restart Dify Services

```bash
cd docker
docker compose restart api worker worker_beat
```

Wait 10-15 seconds for services to restart.

#### B2.4 Verify in Dify UI

1. Go to http://localhost
2. Open your knowledge bases
3. Try "Retrieval Testing"
4. **Should work without "default named vector" errors!** 

---

## Troubleshooting

### Path A: Backup fails with "no available classes"

**Cause:** Weaviate not ready or no collections exist

**Solution:**
```bash
# Check if Weaviate is running
docker compose ps weaviate

# Check if collections exist
curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/schema" | python3 -m json.tool
```

### Path A: Restore fails with "backup not found"

**Cause:** Backup files not accessible in new version

**Solution:**
```bash
# Verify backup files exist
ls -la docker/volumes/weaviate_backups/kb-backup/

# Check permissions
sudo chmod -R 755 docker/volumes/weaviate_backups/
```

### Path B: Still showing 0 objects after LSM fix

**Cause:** Data not copied correctly or permission issues

**Solution:**
```bash
# Check if data was copied
ls -lh docker/volumes/weaviate/vector_index_*/*/lsm/objects/*.db

# Fix permissions
chmod -R 755 docker/volumes/weaviate/vector_index_*

# Check Weaviate logs
docker compose logs weaviate | tail -50
```

### Migration script shows 0 objects to migrate

**Cause:** LSM fix didn't work or data not accessible

**Solution:**
1. Verify you ran LSM fix correctly
2. Restart Weaviate: `docker compose restart weaviate`
3. Wait 30 seconds
4. Check object count again
5. If still 0, check logs: `docker compose logs weaviate`

### Can I rollback to 1.19?

**NO!** Rolling back will NOT work:
- Weaviate 1.27+ uses RAFT-based schema management
- schema.db format is incompatible with 1.19
- Rolling back causes total failure ("no schema present")
- **Solution:** Stay on 1.27+ and follow Path B

---

## Cleanup (Optional)

After successful migration:

### Delete backup files (Path A)
```bash
rm -rf docker/volumes/weaviate_backups/
```

### Delete orphaned LSM directories (Both paths)
```bash
cd docker/volumes/weaviate
rm -rf vector_index_*_node_*_lsm
echo "✓ Orphaned LSM directories removed"
```

### Delete temporary files
```bash
rm -rf weaviate_migration_env/
```

---

## Summary

### Path A (With Backup):
1. Enable backup module on 1.19
2. Backup data using Weaviate API
3. Upgrade to 1.27+
4. Restore backup
5. Fix orphaned LSM data (if needed)
6. Run migration script
7. Restart Dify services

**Result:** Zero data loss, safest approach

### Path B (Direct Recovery):
1. Fix orphaned LSM data
2. Run migration script
3. Restart Dify services

**Result:** Data recovered without backup

### What Gets Preserved:
- All document text and metadata
- All vector embeddings (no re-indexing!)
- All UUIDs and relationships
- All knowledge base settings

### What Changes:
- Schema format: `vectorizer: none` → `vectorConfig: {default: {...}}`
- Storage structure: Flat → Nested (1.27+)
- Weaviate version: 1.19 → 1.27/1.33

---

## Files Needed

- `migrate_weaviate_collections.py` - Schema migration script (included in repo)

## Credits

- Original migration approach: Dify team
- LSM recovery method: Chinese Dify community user
- Combined solution: Community effort
