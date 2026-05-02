# CS172 Project - BlueSky Post Collector
A simplified social network search engine

## How to Use
To use, run this command:
```./run_collector.bat --seed <FILE_PATH/FILE_NAME.EXT> --max-users <NUM> --max-posts <NUM> --max-followers <NUM> --out <DIR> --max-size <NUM>```

where:
- `--seed` specifies the file that contains the starting point of the collector
- `--max-users` specifies how many users the collector should crawl
- `--max-posts` specifies how many posts the collector should fetch per user
- `--max-followers` specifies how many followers the collector should fetch per user
- `--out` specifies where to store the data files (.ndjson)
- `--max-size` specifies the limit of how much data to collect (in KB)

### Example
If you wanted to run the collector that only crawls up to 100 people and fetches 10 posts and followers per person with a max storage size of 5MB:
```./run_collector.bat --seed src/seed_file.json --max-users 100 --max-posts 10 --max-followers 10 --out data/ --max-size 5242880```
