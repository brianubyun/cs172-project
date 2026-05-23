import sys
from pathlib import Path
from elasticsearch import Elasticsearch

MAPPING = {
    "mappings": {
        "properties": {
            "post_id": {"type": "keyword"},
            "content_id": {"type": "keyword"},
            "text": {"type": "text", "analyzer": "english"},
            "urls": {"type": "keyword"},
            # images is flattened from a list of dicts to just a list (only a fullsize key)
            "images": {"type": "keyword"},
            "embedded_url": {"type": "keyword"},
            "embedded_title": {"type": "text", "analyzer": "english"},
            "embedded_description": {"type": "text", "analyzer": "english"},
            "username": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "likes": {"type": "integer", "ignore_malformed": True},
            "reposts": {"type": "integer", "ignore_malformed": True},
            "replies": {"type": "integer", "ignore_malformed": True},
        }
    }
}

def create_index(es, idx):
    # remove old index
    if es.indices.exists(index=idx):
        es.indices.delete(index=idx)
        print(f"deleted existing index '{idx}'")

    # create index with our mappings
    es.indices.create(index=idx, mappings=MAPPING["mappings"])
    print(f"created index '{idx}'")

def main():
    # where our data lies
    dir = Path("data")
    # the index name
    idx = "bluesky_posts"
    # the local endpoint
    es_host = "http://127.0.0.1:9200"

    if not dir.exists() or not dir.is_dir():
        print("dir not found:", dir)
        sys.exit(1)

    es = Elasticsearch(es_host)
    try:
        if not es.ping():
            print("es not reachable at ", es_host)
            sys.exit(1)
    except Exception as e:
        print("error with es:", e)
        sys.exit(1)

    create_index(es, idx)

if __name__ == "__main__":
    main()
