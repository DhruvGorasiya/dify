#!/bin/bash

WEAVIATE_URL="http://localhost:8080"
API_KEY="WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih"

echo "Finding collections with OLD schema..."
OLD_COLLECTIONS=$(curl -s -H "Authorization: Bearer $API_KEY" \
  "$WEAVIATE_URL/v1/schema" | python3 -c "
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

echo "Collections to delete:"
echo "$OLD_COLLECTIONS"
echo ""
echo "Total: $(echo "$OLD_COLLECTIONS" | wc -l | tr -d ' ') collections"
echo ""
read -p "Are you sure you want to delete these collections? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Deleting collections..."
while IFS= read -r collection; do
    if [ -n "$collection" ]; then
        echo "  Deleting: $collection"
        curl -X DELETE \
          -H "Authorization: Bearer $API_KEY" \
          "$WEAVIATE_URL/v1/schema/$collection"
        echo ""
    fi
done <<< "$OLD_COLLECTIONS"

echo ""
echo "Done! All old schema collections have been deleted."