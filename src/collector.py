import os                       # Used for file manipulation (creating new data file per 10MB)
import json                     # Used for reading/opening JSON files
import time                     # sleep() function
from collections import deque   # Used data structure as frontier
import re                       # Used for regular expressions (to extract URLs)
import requests                 # Used for making HTTP requests (internet communication)
from bs4 import BeautifulSoup   # HTML Parser (convert HTML to string)
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Global Variables ---
# Base URL for calling Bluesky API
BASE = "https://public.api.bsky.app/xrpc/"
# Regular expression for extracting URLS
URL_RE = re.compile(r'https?://\S+')
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "BlueskyCollector"})

# workers based on CPU count
NUM_PAGE_TITLE_WORKERS = min(24, max(8, os.cpu_count() or 1))
# this is the thread pool
title_fetcher_executor = ThreadPoolExecutor(max_workers=NUM_PAGE_TITLE_WORKERS)
# dict for (URL -> title) cache
url_title_cache = {}
# it is possible for multiple threads to access the same memory simultaneously
title_cache_lock = threading.Lock()
# per thread storage for each worker to have its own requests.Session
thread_session_store = threading.local()
# sentinel
NOT_CACHED = object()

# Find all URLs within a post's content
def extractURL(text):
    # If null
    if not text:
        return []
    
    # Retrieve all URLs found as a list
    return URL_RE.findall(text)

# get or create a thread-local requests session for page title fetching
# we need this because requests sessions are not thread-safe
def get_thread_session():
    # see if session exists for the curen thread
    session = getattr(thread_session_store, "session", None)
    if session is None:
        # create the new session
        session = requests.Session()
        session.headers.update({"User-Agent": "BlueskyCollector"})
        thread_session_store.session = session
    return session

# read a cached title safely
def get_cached_title(url):
    with title_cache_lock:
        return url_title_cache.get(url, NOT_CACHED)

# write a cached title safely
def cache_page_title(url, title):
    with title_cache_lock:
        url_title_cache[url] = title

# retry wrapper
def call_with_retry(func, *args, retries=3, base_delay=0.2, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except requests.exceptions.RequestException:
            if attempt == retries:
                raise
            time.sleep(base_delay * attempt)

# Fetch page title from a URL
def get_page_title(url):
    try:
        session = get_thread_session()

        # Use separate connect/read timeouts to fail fast on dead hosts.
        resp = session.get(url, timeout=(0.25, 0.4))
        resp.raise_for_status()

        # Only download first 500KB of data
        html = resp.text[:500_000]

        # Call the HTML parser
        soup = BeautifulSoup(html, "html.parser")

        # If title tag and content exists, return title
        if soup.title and soup.title.string:
            return soup.title.string.strip()
    except Exception:
        return None
    return None

# Get required fields for a post (ID, content, URLs, images)
def extractFields(post):
    # Post ID
    uri = post.get("uri")

    # Content ID
    cid = post.get("cid")

    # Text / Post Content
    text = post.get("record", {}).get("text", "")

    # Call helper function to extract all URLs
    urls = extractURL(text)

    # Images
    images = []
    # Search inside the embedded area
    embed = post.get("embed", {})

    # If the embedded media is an image
    if embed.get("$type") == "app.bsky.embed.images#view":
        # Loop through all images and get image
        for img in embed.get("images", []):
            images.append({
                "fullsize": img.get("fullsize")
            })

    # A lot of times, users will embed URLs into their posts rather than leaving it as plaintext
    # Search the embedded area for URLs
    embedded_url = None
    embedded_title = None
    embedded_description = None

    # If the embedded media points outside Blueksy (an outside URL)
    if embed.get("$type") == "app.bsky.embed.external#view":
        ext = embed.get("external", {})
        embedded_url = ext.get("uri")
        embedded_title = ext.get("title")
        embedded_description = ext.get("description")

        # Add embedded URL to the URL list
        if embedded_url:
            urls.append(embedded_url)

    # Post Statistics
    like_count = post.get("likeCount")
    repost_count = post.get("repostCount")
    reply_count = post.get("replyCount")

    # Username
    username = post.get("author", {}).get("handle")

    # Timestamp
    timestamp = post.get("record", {}).get("createdAt")

    # Data to return
    return {
        "post_id": uri,
        "content_id": cid,
        "text": text,
        "urls": urls,
        "images": images,
        "embedded_url": embedded_url,
        "embedded_title": embedded_title,
        "embedded_description": embedded_description,
        "username": username,
        "timestamp": timestamp,
        "likes": like_count,
        "reposts": repost_count,
        "replies": reply_count
    }

class StorePosts:
    """
    Class dedicated to how we allocate and manage storage of posts.
    One post per row; 10MB of data per file

    """
    def __init__(self, directory="data", max_mb=10):
        self.directory = directory

        # Make directory if doesn't exist
        os.makedirs(directory, exist_ok=True)

        # Set max size of a file
        self.max_bytes = max_mb * 1024 * 1024

        # Store what file we're currently storing to
        self.current_file = None

        # File size
        self.current_size = 0

        # Used for labeling files
        self.index = 0
        for filename in os.listdir(directory):
            if filename.startswith("posts_") and filename.endswith(".ndjson"):
                try:
                    index = int(filename[6:11])
                    self.index = max(self.index, index + 1)
                except (ValueError, IndexError):
                    pass

    def _open_new(self):
        # Close open file
        if self.current_file:
            self.current_file.close()

        # Create path name for file (with 5 decimal padding)
        path = os.path.join(self.directory, f"posts_{self.index:05d}.ndjson")

        # Set current file to new file and open for writing
        self.current_file = open(path, "w", encoding="utf-8")

        self.current_size = 0
        self.index += 1

    def write(self, line):
        # For the first write, open file
        if self.current_file is None:
            self._open_new()

        # Get size of content (everything from extractFields)
        size = len(line.encode("utf-8"))

        # If writing to this file exceeds current size limit (10MB), open a new file
        if self.current_size + size > self.max_bytes:
            self._open_new()

        # Write to file and update size
        self.current_file.write(line)
        self.current_size += size

    def close(self):
        # Useful for closing the final file (because it won't naturally close from open_new if it's the last file)
        if self.current_file:
            self.current_file.close()

# Get a post from a user handle
def fetchPost(handle, cursor=None, limit=100):
    # Custom struct 
    params = {
        "actor": handle,
        "limit": limit
    }

    # If given a cursor (current index for pagination -- breaking something up into smaller pieces)
    if cursor:
        params["cursor"] = cursor

    # Piece together BASE url and FEED url to make API call (this is where we're searching for posts)
    url = BASE + "app.bsky.feed.getAuthorFeed"

    # Make HTTP request; wait 4 seconds
    try:
        resp = SESSION.get(url, params=params, timeout=4)
        resp.raise_for_status() # Throw exception in case the request fails
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and limit > 100:
            params["limit"] = 100
            resp = SESSION.get(url, params=params, timeout=4)
            resp.raise_for_status()
        else:
            raise

    # Turn the response (whatever Bluesky gave us) into JSON file for easy reading
    data = resp.json()

    # Extract the feed (this is where the posts are)
    feed = data.get("feed", [])
    next_cursor = data.get("cursor")

    # Extract the post objects from feed items
    posts = []
    for item in feed:
        post = item.get("post")
        if post:
            posts.append(post)

    return posts, next_cursor

def getFollowers(handle, cursor=None, limit=100):
    # Custom struct 
    params = {
        "actor": handle,
        "limit": limit
    }

    # If given a cursor (current index for pagination -- breaking something up into smaller pieces)
    if cursor:
        params["cursor"] = cursor

    # Piece together BASE url and FOLLOWER url to make API call (this is where we're searching for posts)
    url = BASE + "app.bsky.graph.getFollowers"

    # Make HTTP request; wait 4 seconds
    try:
        resp = SESSION.get(url, params=params, timeout=4)
        resp.raise_for_status() # Throw exception in case the request fails
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400 and limit > 100:
            params["limit"] = 100
            resp = SESSION.get(url, params=params, timeout=4)
            resp.raise_for_status()
        else:
            raise

    # Turn the response (whatever Bluesky gave us) into JSON file for easy reading
    data = resp.json()

    # Extract follower list
    followers = data.get("followers", [])
    next_cursor = data.get("cursor")

    # Extract handles
    handles = []
    for f in followers:
        if f.get("handle"):
            handles.append(f.get("handle"))

    return handles, next_cursor

# For a given user, fetch their posts and crawl their followers for their posts
def crawl(max_users=10000, seed_file="seed_file.json", max_posts=100, max_followers=100, output_dir="data", max_size=524288000):
    """
    Starting from a list of seed user(s):
    - fetch posts
    - extract fields
    - store posts
    - fetch followers
    - add followers to frontier
    """

    # Keeping track of current data size
    total_bytes = 0

    # Open Seed File with base users
    with open(seed_file) as f:
        seed_users = json.load(f)

    # Declare deque (follows BFS)
    frontier = deque(seed_users)

    # Prevent duplicates (sets require unique keys)
    visited = set()

    # Instantiate our StorePosts class to store posts
    writer = StorePosts(directory=output_dir)

    try:
        # Keep looping while we still have users to visit or maximum amount of users crawled
        # Alternatively we can also end if we reach the max_size of data we want to scrape
        while frontier and len(visited) < max_users:
            # Get first user
            user = frontier.popleft()

            # If visited, skip
            if user in visited:
                continue

            visited.add(user)

            # Logging
            print(f"Processing user: {user}")

            # Fetch posts
            cursor = None
            posts_col = 0
            # Keep looping if using pagination (something broken into multiple parts)
            while True:
                rem_posts = max_posts - posts_col
                if rem_posts <= 0:
                    break

                # Catch exception if API call fails
                try:
                    posts, cursor = call_with_retry(fetchPost, user, cursor, limit=rem_posts)
                except Exception as e:
                    print(f"Error fetching posts for {user}: {e}")
                    break

                # For these fetched posts, extract information
                for post in posts:
                    if posts_col >= max_posts:
                        break

                    # Get data we want from a post
                    post_data = extractFields(post)

                    # For all URLs, extract the page title in parallel with caching
                    page_titles = {}
                    if post_data["urls"]:
                        # deduplicate URLs and keep the original order
                        unique_urls = list(dict.fromkeys(post_data["urls"]))

                        urls_needing_titles = []
                        for url in unique_urls:
                            # if we already have the title for the embedded URL, reuse it
                            if post_data.get("embedded_url") == url and post_data.get("embedded_title"):
                                title = post_data["embedded_title"]
                                page_titles[url] = title
                                cache_page_title(url, title)
                                continue
                            
                            cached_value = get_cached_title(url)
                            if cached_value is NOT_CACHED:
                                urls_needing_titles.append(url)
                            else:
                                page_titles[url] = cached_value

                        # submits all the URLS with missing titles to the thread pool to get their titles
                        futures_by_url = {
                            title_fetcher_executor.submit(get_page_title, url): url
                            for url in urls_needing_titles
                        }

                        # iterate through the futures as they finish
                        for future in as_completed(futures_by_url):
                            url = futures_by_url[future]
                            try:
                                title = future.result()
                            except Exception:
                                title = None

                            page_titles[url] = title
                            cache_page_title(url, title)
                    post_data["page_titles"] = page_titles

                    # Convert to a JSON line (to write to file)
                    line = json.dumps(post_data, ensure_ascii=False) + "\n"

                    # Write to file and calculate size
                    size = len(line.encode("utf-8"))
                    writer.write(line)
                    total_bytes += size
                    posts_col += 1

                    # If max_size is reached, end
                    if total_bytes >= max_size:
                        print("Reached data size limit.")
                        return

                # If pagination was not used (or ended), leave loop
                if not cursor:
                    break

            # Fetch followers and add to frontier
            cursor = None
            followers_col = 0
            # Keep looping if using pagination (something broken into multiple parts)
            while True:
                rem_followers = max_followers - followers_col
                if rem_followers <= 0:
                    break

                # Catch exception if API call fails
                try:
                    followers, cursor = call_with_retry(getFollowers, user, cursor, limit=rem_followers)
                except Exception as e:
                    print(f"Error fetching followers for {user}: {e}")
                    break

                # For a follower, check if visited
                for follower in followers:
                    if followers_col >= max_followers:
                        break

                    followers_col += 1
                    if follower not in visited:
                        frontier.append(follower)

                # If pagination was not used (or ended), leave loop
                if not cursor:
                    break

            # Small delay every iteration to avoid abusing API calls
            time.sleep(0.01)

        print("Crawl complete.")
    finally:
        writer.close()
        title_fetcher_executor.shutdown(wait=True)
