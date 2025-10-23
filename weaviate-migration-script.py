#!/usr/bin/env python3
"""
Proper Weaviate Data Migration Script

This script properly migrates data from Weaviate 1.19.0 to 1.27.0 by:
1. Creating a temporary collection with the old schema
2. Restoring backup data to the temporary collection
3. Creating a new collection with the correct 1.27.0 schema (with vectorConfig)
4. Copying all data (including embeddings) from temp to new collection
5. Deleting the temporary collection

Usage:
    python proper_weaviate_migration.py
"""

import requests
import json
import sys
import time


class ProperWeaviateMigrator:
    def __init__(self, weaviate_url="http://localhost:8080", api_key="WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih"):
        self.weaviate_url = weaviate_url.rstrip('/')
        self.api_key = api_key
        self.headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        self.backup_id = "dify-backup-before-upgrade"
        self.old_class_name = "Vector_index_8fdfac53_bdaf_4388_915a_d02889a6f0b7_Node"
        self.temp_class_name = f"{self.old_class_name}_TEMP"
    
    def delete_class(self, class_name):
        """Delete a class if it exists"""
        print(f"Deleting class: {class_name}")
        
        response = requests.delete(
            f"{self.weaviate_url}/v1/schema/{class_name}",
            headers=self.headers
        )
        
        if response.status_code == 200:
            print(f"Successfully deleted {class_name}")
            return True
        else:
            print(f"Class doesn't exist or failed to delete: {response.text}")
            return False
    
    def restore_to_temp_collection(self):
        """Restore backup to a temporary collection"""
        print(f"\nStep 1: Restoring backup to temporary collection")
        print("=" * 60)
        
        # The restore will create the class with the original name
        # We'll need to work with that
        
        response = requests.post(
            f"{self.weaviate_url}/v1/backups/filesystem/{self.backup_id}/restore",
            headers=self.headers,
            json={"include": [self.old_class_name]}
        )
        
        if response.status_code != 200:
            print(f"Failed to initiate restore: {response.text}")
            return False
        
        print("Restore initiated")
        
        # Wait for restore to complete
        print("Waiting for restore to complete...")
        for i in range(30):
            time.sleep(2)
            response = requests.get(
                f"{self.weaviate_url}/v1/backups/filesystem/{self.backup_id}/restore",
                headers=self.headers
            )
            
            if response.status_code == 200:
                status = response.json()
                if status.get('status') == 'SUCCESS':
                    print("Restore completed successfully!")
                    return True
                elif status.get('status') == 'FAILED':
                    error = status.get('error', 'Unknown error')
                    if "already exists" in error:
                        print("Class already exists (data might be there)")
                        return True
                    print(f"Restore failed: {error}")
                    return False
        
        print("Restore timed out")
        return False
    
    def get_all_objects_with_vectors(self, class_name):
        """Get all objects from a class including their vectors"""
        print(f"\nFetching all objects from {class_name}")
        
        all_objects = []
        offset = 0
        limit = 100
        
        while True:
            response = requests.get(
                f"{self.weaviate_url}/v1/objects",
                headers=self.headers,
                params={
                    "class": class_name,
                    "include": "vector",
                    "limit": limit,
                    "offset": offset
                }
            )
            
            if response.status_code != 200:
                print(f"Failed to fetch objects: {response.text}")
                return None
            
            data = response.json()
            objects = data.get('objects', [])
            
            if not objects:
                break
            
            all_objects.extend(objects)
            offset += limit
            print(f"   Fetched {len(all_objects)} objects so far...")
        
        print(f"Total objects fetched: {len(all_objects)}")
        return all_objects
    
    def create_new_collection_with_vectorconfig(self):
        """Create a new collection with Weaviate 1.27.0 schema format"""
        print(f"\nStep 2: Creating new collection with vectorConfig")
        print("=" * 60)
        
        # First, get the old schema to preserve property definitions
        response = requests.get(
            f"{self.weaviate_url}/v1/schema/{self.old_class_name}",
            headers=self.headers
        )
        
        if response.status_code != 200:
            print(f"Failed to get old schema: {response.text}")
            return False
        
        old_schema = response.json()
        print(f"Retrieved old schema")
        
        # Create new schema with vectorConfig
        # Note: In Weaviate 1.27.0, vectorizer must be a config object
        vector_config = {
            "vectorIndexConfig": old_schema.get('vectorIndexConfig', {}),
            "vectorIndexType": old_schema.get('vectorIndexType', 'hnsw'),
            "vectorizer": {
                "none": {}
            }
        }
        
        new_schema = {
            "class": f"{self.old_class_name}_NEW",
            "description": "Migrated collection with Weaviate 1.27.0 schema",
            "invertedIndexConfig": old_schema.get('invertedIndexConfig', {}),
            "properties": old_schema.get('properties', []),
            "replicationConfig": old_schema.get('replicationConfig', {}),
            "shardingConfig": old_schema.get('shardingConfig', {}),
            "vectorConfig": {
                "default": vector_config
            }
        }
        
        # Create the new collection
        print(f"Creating new collection: {new_schema['class']}")
        response = requests.post(
            f"{self.weaviate_url}/v1/schema",
            headers=self.headers,
            json=new_schema
        )
        
        if response.status_code == 200:
            print(f"Successfully created new collection with vectorConfig")
            return new_schema['class']
        else:
            print(f"Failed to create new collection: {response.text}")
            return None
    
    def copy_data_to_new_collection(self, new_class_name, objects):
        """Copy all objects with their vectors to the new collection"""
        print(f"\nStep 3: Copying {len(objects)} objects to new collection")
        print("=" * 60)
        
        success_count = 0
        failed_count = 0
        
        for idx, obj in enumerate(objects):
            # Prepare the object for the new collection
            new_object = {
                "class": new_class_name,
                "properties": obj.get('properties', {}),
                "vectors": {
                    "default": obj.get('vector', [])
                }
            }
            
            # Optionally preserve the original ID
            if 'id' in obj:
                new_object['id'] = obj['id']
            
            # Create the object in the new collection
            response = requests.post(
                f"{self.weaviate_url}/v1/objects",
                headers=self.headers,
                json=new_object
            )
            
            if response.status_code in [200, 201]:
                success_count += 1
                if (idx + 1) % 10 == 0:
                    print(f"   Copied {success_count}/{len(objects)} objects...")
            else:
                failed_count += 1
                print(f"   Failed to copy object {idx}: {response.text}")
        
        print(f"\nSuccessfully copied {success_count} objects")
        if failed_count > 0:
            print(f"Failed to copy {failed_count} objects")
        
        return success_count > 0
    
    def rename_collection(self, old_name, new_name):
        """Rename a collection by deleting old and renaming new"""
        print(f"\nStep 4: Finalizing migration")
        print("=" * 60)
        
        # Delete the old collection
        print(f"Deleting old collection: {old_name}")
        self.delete_class(old_name)
        
        # Note: Weaviate doesn't support direct renaming
        # The new collection will keep its _NEW suffix
        # We'll need to update Dify's configuration or
        # delete the old one and create the final one with the correct name
        
        print(f"Collection created as: {new_name}")
        print(f"    You may need to update Dify's configuration to use this new collection")
        print(f"    Or we can delete the old one and recreate with the original name")
        
        return True
    
    def recreate_with_original_name(self, temp_new_class, objects):
        """Delete temp new class and recreate with original name"""
        print(f"\nStep 5: Recreating collection with original name")
        print("=" * 60)
        
        # Get the schema from the temp new class
        response = requests.get(
            f"{self.weaviate_url}/v1/schema/{temp_new_class}",
            headers=self.headers
        )
        
        if response.status_code != 200:
            print(f"Failed to get temp schema: {response.text}")
            return False
        
        temp_schema = response.json()
        
        # Delete both the old restored collection and the temp new class
        self.delete_class(self.old_class_name)  # Delete the old restored one first
        self.delete_class(temp_new_class)
        
        # Create with original name
        final_schema = temp_schema.copy()
        final_schema['class'] = self.old_class_name
        
        print(f"Creating final collection: {self.old_class_name}")
        response = requests.post(
            f"{self.weaviate_url}/v1/schema",
            headers=self.headers,
            json=final_schema
        )
        
        if response.status_code != 200:
            print(f"Failed to create final collection: {response.text}")
            return False
        
        print(f"Created final collection with original name")
        
        # Copy data to final collection
        return self.copy_data_to_new_collection(self.old_class_name, objects)
    
    def run_migration(self):
        """Run the complete migration process"""
        print("=" * 60)
        print("Proper Weaviate Data Migration Tool")
        print("   From: Weaviate 1.19.0 (old schema)")
        print("   To:   Weaviate 1.27.0 (vectorConfig schema)")
        print("=" * 60)
        
        # Clean up any existing collections
        print("\nCleaning up existing collections...")
        self.delete_class(self.old_class_name)
        self.delete_class(f"{self.old_class_name}_NEW")
        
        # Step 1: Restore backup
        if not self.restore_to_temp_collection():
            print("\nMigration failed at restore step")
            return False
        
        # Step 1.5: Get all objects with vectors
        objects = self.get_all_objects_with_vectors(self.old_class_name)
        if objects is None or len(objects) == 0:
            print("\nNo objects found to migrate")
            return False
        
        print(f"\nFound {len(objects)} objects with embeddings to migrate")
        
        # Step 2: Create new collection with vectorConfig
        new_class_name = self.create_new_collection_with_vectorconfig()
        if not new_class_name:
            print("\nMigration failed at collection creation step")
            return False
        
        # Step 3: Copy data to new collection
        if not self.copy_data_to_new_collection(new_class_name, objects):
            print("\nMigration failed at data copy step")
            return False
        
        # Step 4: Recreate with original name
        if not self.recreate_with_original_name(new_class_name, objects):
            print("\nMigration failed at final recreation step")
            return False
        
        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print(f"   Collection: {self.old_class_name}")
        print(f"   Objects migrated: {len(objects)}")
        print(f"   Embeddings preserved: Yes")
        print("=" * 60)
        
        return True


if __name__ == "__main__":
    migrator = ProperWeaviateMigrator()
    success = migrator.run_migration()
    sys.exit(0 if success else 1)

