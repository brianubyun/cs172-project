#!/usr/bin/env python3

import argparse                 # Library for creating command line arguments
from collector import crawl     # Import crawl function from collector.py

def main():
    # Create arugment parser to understand parameters passed
    parser = argparse.ArgumentParser(description="Bluesky Crawler")

    # Declare a field for defining seed file
    parser.add_argument(
        "--seed",
        type=str,
        required=True,
        help="Path to seed file (JSON list of handles)"
    )

    # Declare a field for defining max users
    parser.add_argument(
        "--max-users",
        type=int,
        default=10000,
        help="Maximum number of users to crawl"
    )

    # Declare a field for defining max posts
    parser.add_argument(
        "--max-posts",
        type=int,
        default=100,
        help="Maximum number of posts to fetch from one user"
    )

    # Declare a field for defining max followers
    parser.add_argument(
        "--max-followers",
        type=int,
        default=100,
        help="Maximum number of followers to fetch from one user"
    )

    # Declare a field for defining output directory for data
    parser.add_argument(
        "--out",
        type=str,
        default="data",
        help="Output directory for NDJSON files"
    )

    # Declare a field for defining max data size of collector
    parser.add_argument(
        "--max-size",
        type=int,
        default=524288000,
        help="Maximum amount of data collector should scrape (bytes)"
    )

    # Pass our arguments
    args = parser.parse_args()

    # Call crawl function
    crawl(
        max_users=args.max_users,
        max_posts=args.max_posts,
        max_followers=args.max_followers,
        seed_file=args.seed,
        output_dir=args.out,
        max_size=args.max_size
    )

if __name__ == "__main__":
    main()
