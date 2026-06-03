import json
import sys
import hashlib
from pathlib import Path
from elasticsearch import Elasticsearch, helpers

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

def ndjson_files(dir):
    for p in sorted(dir.glob("posts_*.ndjson")):
        yield p

def iter_docs(path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue

            # Extract clean username (without .bluesky.social or other metadata)
            raw_username = obj.get("username", "")
            username_clean = raw_username.split(".")[0]

            # normalize the document to have a consistent shape
            doc = {
                "post_id": obj.get("post_id"),
                "content_id": obj.get("content_id"),
                "text": obj.get("text"),
                "urls": obj.get("urls", []),
                # get fullsize image urls from images list
                # this will convert them from a list of dictonaries with fullsize keys to just lists of urls
                "images": [
                    img.get("fullsize")
                    for img in obj.get("images", [])
                    if isinstance(img, dict) and img.get("fullsize")
                ],
                "embedded_url": obj.get("embedded_url"),
                "embedded_title": obj.get("embedded_title"),
                "embedded_description": obj.get("embedded_description"),
                "username": obj.get("username"),
                "username_clean": username_clean,
                "timestamp": obj.get("timestamp"),
                "likes": obj.get("likes"),
                "reposts": obj.get("reposts"),
                "replies": obj.get("replies"),
                # page_titles creates a dynamic mapping URL -> title, which will cause the index size to explode. So do not index this field
            }

            # use content_id as default, then post_id
            # if neither exist, generate an id from the object
            # when i checked, all docs had a content_id, so this is a sanity check
            doc_id = obj.get("content_id") or obj.get("post_id")
            if not doc_id:
                c = json.dumps(obj, sort_keys=True, separators=(",", ":"))
                doc_id = "gen:" + hashlib.sha1(c.encode("utf-8")).hexdigest()

            yield doc_id, doc
            
def create_index(es, idx):
    # remove old index
    if es.indices.exists(index=idx):
        es.indices.delete(index=idx)
        print(f"deleted existing index '{idx}'")

    # create index with our mappings
    es.indices.create(index=idx, mappings=MAPPING["mappings"])
    print(f"created index '{idx}'")

def index_batch(es, idx, docs, b_size):
    actions = []
    cnt = 0
    seen = set()

    for doc_id, doc in docs:
        # keep first document seen - prevents dupes
        # dupes would be prevented anyway because we set _id, but this is more efficient because it is client side dedupe
        if doc_id in seen:
            continue
        seen.add(doc_id)
    
        # action for bulk API
        # required
        action = {"_index": idx, "_source": doc}

        if doc_id:
            action["_id"] = doc_id
            
        actions.append(action)

        if len(actions) >= b_size:
              # send the batch to Elasticsearch
            helpers.bulk(es, actions)
            cnt += len(actions)
            print(f"indexed {cnt} docs...")
            actions = []

    if actions:
        # send the last actions to Elasticsearch
        helpers.bulk(es, actions)
        cnt += len(actions)
    return cnt

def main():
    # where our data lies
    dir = Path("data")
    # the index name
    idx = "bluesky_posts"
    # the local endpoint
    es_host = "http://127.0.0.1:9200"
    # batches of about 3MB
    b_size = 5000

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

    total = 0
    for path in ndjson_files(dir):
        # generator for each document in the file
        docs = iter_docs(path)
        
        cnt = index_batch(es, idx, docs, b_size)
        
        total += cnt
        print(f"finished indexing {path.name}: {cnt} docs")

    print(f"total docs indexed: {total}")

if __name__ == "__main__":
    main()
