@echo off
echo === Starting Elasticsearch (Docker) ===

REM Check if container exists
docker ps -a --format "{{.Names}}" | findstr /I "elasticsearch" >nul

@REM Check if container exists, if not create one
IF %ERRORLEVEL%==0 (
    echo Elasticsearch container already exists. Starting it...
    docker start elasticsearch
) ELSE (
    echo Elasticsearch container not found. Creating a new one...
    docker run -d --name elasticsearch ^
        -p 9200:9200 ^
        -e "discovery.type=single-node" ^
        -e "xpack.security.enabled=false" ^
        docker.elastic.co/elasticsearch/elasticsearch:8.11.1
)

echo Waiting for Elasticsearch to be ready...

@REM Wait for ElasticSearch to be ready or else indexes can't be made
:waitloop
curl -s http://127.0.0.1:9200 >nul
IF %ERRORLEVEL%==0 (
    echo Elasticsearch is ready!
) ELSE (
    echo ...
    timeout /t 5 >nul
    goto waitloop
)

echo === Creating Index ===
python ./src/create_index.py
