#!/bin/bash

BACKUP_ID="dify-backup"

echo "Finding collections with OLD schema (Weaviate 1.19)..."
OLD_COLLECTIONS=$(curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/schema" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for cls in data.get('classes', []):
    if cls['class'].startswith('Vector_index_') and 'vectorConfig' not in cls:
        print(cls['class'])
")

if [ -z "$OLD_COLLECTIONS" ]; then
    echo "No collections with old schema found!"
    exit 0
fi

echo "Collections to backup:"
echo "$OLD_COLLECTIONS"
echo ""
echo "Total: $(echo "$OLD_COLLECTIONS" | wc -l | tr -d ' ') collections"
echo ""
echo "Backup ID: $BACKUP_ID"
echo ""
read -p "Are you sure you want to backup these collections? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Creating backup with ID: $BACKUP_ID"
echo "This will backup all old collections in one backup file..."

# Convert collection list to JSON array format
COLLECTIONS_JSON=$(echo "$OLD_COLLECTIONS" | python3 -c "
import sys, json
collections = [line.strip() for line in sys.stdin if line.strip()]
print(json.dumps(collections))
")

# Create backup for all collections at once
curl -X POST \
  -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  -H "Content-Type: application/json" \
  "http://localhost:8080/v1/backups/filesystem" \
  -d "{
  \"id\": \"$BACKUP_ID\",
  \"include\": $COLLECTIONS_JSON
}"

echo ""
echo ""
echo "Checking backup status..."
sleep 2

curl -s -H "Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih" \
  "http://localhost:8080/v1/backups/filesystem/$BACKUP_ID" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('status', 'UNKNOWN')
    print(f'Backup status: {status}')
    if status == 'SUCCESS':
        print('✓ Backup completed successfully!')
        print(f'Backup location: ./volumes/weaviate_backups/{data.get(\"id\", \"\")}')
    elif status == 'FAILED':
        print('✗ Backup failed!')
        print(f'Error: {data.get(\"error\", \"Unknown error\")}')
    else:
        print(f'Status: {status}')
except:
    print('Could not parse backup status')
"

echo ""
echo "Done! Your old schema collections have been backed up."
echo "Backup ID: $BACKUP_ID"
echo ""
echo "Next steps:"
echo "1. Verify backup exists: ls -la docker/volumes/weaviate_backups/"

