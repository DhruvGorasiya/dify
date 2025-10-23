import weaviate

def reproduce_error():
    client = weaviate.connect_to_local(
        host="localhost",
        port=8080,
        grpc_port=50051,
        auth_credentials=weaviate.auth.AuthApiKey("WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih")
    )
    
    try:
        collection_name = "Vector_index_cbc45b19_920b_43e7_b127_6762bdda66ed_Node"
        collection = client.collections.get(collection_name)
        
        # This query triggers the error because it explicitly uses target_vector="default"
        # but the old schema from Weaviate 1.19.0 doesn't have a "default" named vector
        result = collection.query.near_vector(
            near_vector=[0.1] * 1536,
            target_vector="default",
            limit=1
        )
        print(result)
    finally:
        client.close()

if __name__ == "__main__":
    reproduce_error()
