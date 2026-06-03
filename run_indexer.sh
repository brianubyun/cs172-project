#!/bin/bash

echo "=== Starting Elasticsearch (Docker) ==="

# Check if container exists, if not create one
if docker ps -a --format "{{.Names}}" | grep -q "^elasticsearch$"; then
    echo "Elasticsearch container already exists. Starting it..."
    docker start elasticsearch
else
    echo "Elasticsearch container not found. Creating a new one..."
    docker run -d --name elasticsearch \
        -p 9200:9200 \
        -e "discovery.type=single-node" \
        -e "xpack.security.enabled=false" \
        docker.elastic.co/elasticsearch/elasticsearch:8.11.1
fi

echo "Waiting for Elasticsearch to be ready..."

# Wait for ElasticSearch to be ready or else indexes can't be created
until curl -s http://127.0.0.1:9200 >/dev/null; do
    echo "..."
    sleep 5
done

echo "Elasticsearch is ready!"

echo "=== Creating Index ==="
python ./src/create_index.py
