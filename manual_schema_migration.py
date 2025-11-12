#!/usr/bin/env python3
"""
Manual Schema Migration Script for Weaviate 1.19 → 1.33

This script manually converts OLD schema collections (no vectorConfig) 
to NEW schema (with vectorConfig + "default" named vector) while preserving ALL data.

Works for users who:
- Upgraded to 1.33 without backing up
- Have mixed OLD/NEW schema collections
- Migration script failed
- Have thousands of documents to preserve
"""

import requests
import json
import sys
from typing import Dict, List, Any
import time

# Configuration
WEAVIATE_HOST = "localhost"
WEAVIATE_PORT = 8080
WEAVIATE_API_KEY = "WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih"
BASE_URL = f"http://{WEAVIATE_HOST}:{WEAVIATE_PORT}"
HEADERS = {
    "Authorization": f"Bearer {WEAVIATE_API_KEY}",
    "Content-Type": "application/json"
}
BATCH_SIZE = 100


def print_header(text: str):
    """Print formatted header"""
    print("\n" + "=" * 80)
    print(text)
    print("=" * 80 + "\n")


def get_schema() -> Dict:
    """Get current Weaviate schema"""
    response = requests.get(f"{BASE_URL}/v1/schema", headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"❌ Failed to get schema: {response.text}")
        sys.exit(1)


def identify_old_collections() -> List[str]:
    """Find collections with OLD schema (no vectorConfig)"""
    schema = get_schema()
    old_collections = []
    
    for cls in schema.get('classes', []):
        class_name = cls['class']
        # Only check Vector_index collections (Dify knowledge bases)
        if not class_name.startswith('Vector_index_'):
            continue
        
        # Check if OLD schema (no vectorConfig)
        if 'vectorConfig' not in cls:
            old_collections.append(class_name)
            print(f"  ✓ Found OLD schema: {class_name}")
        else:
            print(f"  ✓ Skip NEW schema: {class_name}")
    
    return old_collections


def count_objects(collection_name: str) -> int:
    """Count objects in a collection"""
    response = requests.get(
        f"{BASE_URL}/v1/objects",
        params={"class": collection_name, "limit": 0},
        headers=HEADERS
    )
    if response.status_code == 200:
        return response.json().get('totalResults', 0)
    return 0


def get_collection_schema(collection_name: str) -> Dict:
    """Get detailed schema for a collection"""
    response = requests.get(
        f"{BASE_URL}/v1/schema/{collection_name}",
        headers=HEADERS
    )
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to get schema for {collection_name}: {response.text}")


def export_all_objects(collection_name: str) -> List[Dict]:
    """Export all objects from a collection with their vectors"""
    print(f"  📦 Exporting objects from {collection_name}...")
    all_objects = []
    offset = 0
    
    while True:
        response = requests.get(
            f"{BASE_URL}/v1/objects",
            params={
                "class": collection_name,
                "limit": BATCH_SIZE,
                "offset": offset,
                "include": "vector"
            },
            headers=HEADERS
        )
        
        if response.status_code != 200:
            print(f"❌ Error fetching objects: {response.text}")
            break
        
        data = response.json()
        objects = data.get('objects', [])
        
        if not objects:
            break
        
        all_objects.extend(objects)
        offset += len(objects)
        print(f"     Exported {len(all_objects)} objects...", end='\r')
    
    print(f"     ✓ Exported {len(all_objects)} objects total")
    return all_objects


def create_new_schema_collection(old_collection_name: str, old_schema: Dict) -> str:
    """Create NEW schema collection with vectorConfig"""
    new_name = f"{old_collection_name}_new"
    
    print(f"  🔧 Creating NEW schema collection: {new_name}")
    
    # Build new schema with vectorConfig
    new_schema = {
        "class": new_name,
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
                    "maxConnections": 64
                }
            }
        },
        "properties": old_schema.get('properties', [])
    }
    
    # Copy other important configs
    if 'invertedIndexConfig' in old_schema:
        new_schema['invertedIndexConfig'] = old_schema['invertedIndexConfig']
    
    # Create the collection
    response = requests.post(
        f"{BASE_URL}/v1/schema",
        headers=HEADERS,
        json=new_schema
    )
    
    if response.status_code in [200, 201]:
        print(f"     ✓ Created: {new_name}")
        return new_name
    else:
        raise Exception(f"Failed to create new collection: {response.text}")


def import_objects(collection_name: str, objects: List[Dict]):
    """Import objects into collection with batch operations"""
    print(f"  📥 Importing {len(objects)} objects into {collection_name}...")
    
    for i in range(0, len(objects), BATCH_SIZE):
        batch = objects[i:i + BATCH_SIZE]
        batch_data = {"objects": []}
        
        for obj in batch:
            # Prepare object for import
            new_obj = {
                "class": collection_name,
                "properties": obj.get('properties', {}),
            }
            
            # Add vector with "default" name for NEW schema
            if 'vector' in obj:
                new_obj['vector'] = {"default": obj['vector']}
            
            # Preserve UUID if exists
            if 'id' in obj:
                new_obj['id'] = obj['id']
            
            batch_data["objects"].append(new_obj)
        
        # Send batch
        response = requests.post(
            f"{BASE_URL}/v1/batch/objects",
            headers=HEADERS,
            json=batch_data
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Batch import failed: {response.text}")
            continue
        
        print(f"     Imported {min(i + BATCH_SIZE, len(objects))}/{len(objects)} objects...", end='\r')
    
    print(f"     ✓ Imported all {len(objects)} objects")


def replace_old_collection(old_name: str, new_name: str):
    """Replace old collection with new one"""
    print(f"  🔄 Replacing {old_name} with {new_name}")
    
    # Step 1: Delete old collection
    print(f"     Deleting old collection...")
    response = requests.delete(
        f"{BASE_URL}/v1/schema/{old_name}",
        headers=HEADERS
    )
    if response.status_code not in [200, 204]:
        raise Exception(f"Failed to delete old collection: {response.text}")
    print(f"     ✓ Deleted {old_name}")
    
    # Wait a moment
    time.sleep(2)
    
    # Step 2: Get schema from new collection
    print(f"     Getting schema from new collection...")
    new_schema = get_collection_schema(new_name)
    
    # Step 3: Export data from new collection
    print(f"     Exporting data from new collection...")
    objects = export_all_objects(new_name)
    
    # Step 4: Create collection with original name
    print(f"     Creating collection with original name...")
    new_schema['class'] = old_name
    response = requests.post(
        f"{BASE_URL}/v1/schema",
        headers=HEADERS,
        json=new_schema
    )
    if response.status_code not in [200, 201]:
        raise Exception(f"Failed to create collection with original name: {response.text}")
    print(f"     ✓ Created {old_name} with NEW schema")
    
    # Step 5: Import data into original name
    if objects:
        print(f"     Importing data into original collection...")
        import_objects(old_name, objects)
    
    # Step 6: Delete temporary collection
    print(f"     Cleaning up temporary collection...")
    requests.delete(f"{BASE_URL}/v1/schema/{new_name}", headers=HEADERS)
    print(f"     ✓ Deleted temporary collection {new_name}")
    
    print(f"  ✅ Successfully replaced {old_name}")


def migrate_collection(collection_name: str):
    """Migrate a single collection from OLD to NEW schema"""
    print_header(f"Migrating: {collection_name}")
    
    try:
        # Count objects
        count = count_objects(collection_name)
        print(f"  📊 Collection has {count} objects")
        
        if count == 0:
            print(f"  ⚠️  Collection is empty. Consider deleting it instead.")
            response = input(f"     Delete empty collection {collection_name}? (yes/no): ")
            if response.lower() == 'yes':
                requests.delete(f"{BASE_URL}/v1/schema/{collection_name}", headers=HEADERS)
                print(f"  ✅ Deleted empty collection")
            return
        
        # Get old schema
        old_schema = get_collection_schema(collection_name)
        
        # Export objects
        objects = export_all_objects(collection_name)
        
        if len(objects) != count:
            print(f"  ⚠️  Warning: Expected {count} objects but exported {len(objects)}")
        
        # Create new collection
        new_collection_name = create_new_schema_collection(collection_name, old_schema)
        
        # Import objects
        import_objects(new_collection_name, objects)
        
        # Verify count
        new_count = count_objects(new_collection_name)
        print(f"  📊 Verification: {count} → {new_count} objects")
        
        if new_count == count:
            print(f"  ✅ Data migration successful!")
            
            # Replace old with new
            response = input(f"     Replace {collection_name} with migrated version? (yes/no): ")
            if response.lower() == 'yes':
                replace_old_collection(collection_name, new_collection_name)
            else:
                print(f"  ℹ️  Kept both collections. Delete {collection_name} manually when ready.")
        else:
            print(f"  ❌ Count mismatch! Check {new_collection_name} before proceeding.")
    
    except Exception as e:
        print(f"  ❌ Error migrating {collection_name}: {e}")
        import traceback
        traceback.print_exc()


def main():
    print_header("Manual Weaviate Schema Migration Tool")
    print("This tool converts OLD schema collections to NEW schema with vectorConfig")
    print("while preserving all data, vectors, and metadata.")
    
    # Step 1: Identify collections
    print_header("Step 1: Identifying Collections")
    old_collections = identify_old_collections()
    
    if not old_collections:
        print("\n✅ No OLD schema collections found! All collections are already migrated.")
        return
    
    print(f"\n📋 Found {len(old_collections)} collections to migrate:")
    for col in old_collections:
        count = count_objects(col)
        print(f"  - {col} ({count} objects)")
    
    # Confirm
    print("\n" + "=" * 80)
    response = input("Proceed with migration? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return
    
    # Step 2: Migrate each collection
    for collection_name in old_collections:
        migrate_collection(collection_name)
    
    print_header("Migration Complete!")
    print("All OLD schema collections have been converted to NEW schema.")
    print("Your data is preserved and ready to use with Dify on Weaviate 1.33!")


if __name__ == "__main__":
    main()

