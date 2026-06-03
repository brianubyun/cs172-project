import re   # Regular Expression Library

#Web-based interface with Flask

from flask import Flask, render_template, request
from elasticsearch import Elasticsearch

#Initializing application and also elasticsearch for searching our data
app = Flask(__name__)
es = Elasticsearch("http://127.0.0.1:9200") #Default port 9200 for elastic search
INDEX = "bluesky_posts" #*** I believe use this with ranking part to go through our indexed bluesky posts

#Home page URL or when first accessing home page/local host
@app.route("/")
def home():
    return render_template("index.html", title="Home Page")

#After user submits query via Enter key or Search button submission, routes here to get relevant ranked results and prints it out on browser
@app.route("/search", methods=["GET"]) #Use GET method since query is added to the URL itself and not body 
def search():
    query = request.args.get("query", "").strip()

    if not query: #No query so go back to default home page
        return render_template("index.html", title="Home Page")
    
    # Ranking function using Elasticsearch's function_score (BM25)
    # However, BM25 suffers from lack of semantic relationships between words so rankings are not that accurate
    es_query = {
        "query": {
            "function_score": {
                "query": {
                    "bool": {
                        "should": [
                            {
                                "multi_match": {
                                    "query": query,
                                    # Decide what fields are relevant and weights for relevancy
                                    "fields": [
                                        "username_clean^3",     # Usernames are weighed 3x important
                                        "text^3",               # Text is weighed 3x important
                                        "embedded_title^2",     # Embedded Titles are 2x important
                                        "embedded_description"  # Embedded Descriptions are 1x important
                                    ],
                                    "type": "phrase",           # Match phrases (whole query)
                                    "boost": 10                  # How much it affects score
                                }
                            },
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "username_clean^3",     # Usernames are weighed 3x important
                                        "text^3",               # Text is weighed 3x important
                                        "embedded_title^2",     # Embedded Titles are 2x important
                                        "embedded_description"  # Embedded Descriptions are 1x important
                                    ],
                                    "type": "phrase_prefix",    # Match phrases (partial query)
                                    "boost": 5                  # How much it affects score
                                }
                            },
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "username_clean^3",     # Usernames are weighed 3x important
                                        "text^3",               # Text is weighed 3x important
                                        "embedded_title^2",     # Embedded Titles are 2x important
                                        "embedded_description"  # Embedded Descriptions are 1x important
                                    ],
                                    "type": "best_fields",          # Default BM25 (rank individual words)
                                    "minimum_should_match": "70%"   # How many words should be present to affect relevancy
                                }
                            },
                        ]
                    }
                },
                "score_mode": "sum",        # Sum all boosts together (like, reposts, freshness, etc.)
                "boost_mode": "multiply",   # Multiply query score (from BM25 model) with sum of boosts
                # Declare functions that boost score (not related to semantic relevancy)  
                "functions": [
                    {
                        "gauss": {
                            # Freshness of a post (within 7 days) boosts score
                            "timestamp": {
                                "scale": "7d",
                                "decay": 0.5
                            }
                        }
                    },
                    {
                        # Number of likes a post has boosts score (likes don't mean much)
                        "field_value_factor": {
                            "field": "likes",
                            "factor": 0.01,
                            "modifier": "sqrt",
                            "missing": 0
                        }
                    },
                    {
                        # Number of reposts a post has boosts score (reposts weight more)
                        "field_value_factor": {
                            "field": "reposts",
                            "factor": 0.05,
                            "modifier": "sqrt",
                            "missing": 0
                        }
                    },
                    {
                        # Number of replies a post has boosts score (replies mean engagement)
                        "field_value_factor": {
                            "field": "replies",
                            "factor": 0.1,
                            "modifier": "sqrt",
                            "missing": 0
                        }
                    }
                ]
            }
        },

        # Control how many are returned for query
        "size": 20
    }

    # Execute search
    response = es.search(index=INDEX, body=es_query)
 
    results = [] #List of results
    for hit in response["hits"]["hits"]:
        # Extract just the post_id to reconstruct post URL
        clean_post_id = hit["_source"].get("post_id").split("/")[-1]
        post_url = f"https://bsky.app/profile/{hit["_source"].get("username")}/post/{clean_post_id}"

        results.append({
            "score": round(hit["_score"], 2),
            "text": hit["_source"].get("text"),
            "post_id": hit["_source"].get("post_id"),
            "username": hit["_source"].get("username"),
            "timestamp": hit["_source"].get("timestamp"),
            "likes": hit["_source"].get("likes"),
            "reposts": hit["_source"].get("reposts"),
            "replies": hit["_source"].get("replies"),
            "embedded_url": hit["_source"].get("embedded_url"),
            "embedded_title": hit["_source"].get("embedded_title"),
            "images": hit["_source"].get("images", []),
            "post_url": post_url,
        })

    return render_template("results.html", query=query, results=results)

# Make it known to Flask
@app.template_filter("make_snippet")
def make_snippet(text, query):
    # Snippet Generation for results

    # Build final snippet with gray outer text
    final_snippet = '<p style="color: gray;">'

    # Make everything lowercase for easier matching
    lower_text = text.lower()

    # Split query into word vector
    words = query.lower().split()

    # Sort words by length to prevent highlighting only query substrings
    words = sorted(words, key=len, reverse=True)

    best_idx = None     # Position of best_word
    best_word = None    # Best word

    # Loop through all query words and find matching word from text
    for w in words:
        pos = lower_text.find(w)
        if pos != -1:
            # Choose the earliest match in the text
            if best_idx is None or pos < best_idx:
                best_idx = pos
                best_word = w

    # If no matching query words just print
    if best_idx is None:
        final_snippet += text[:80]
        if(len(text) - 80 > 0):
            final_snippet += "..."
        return final_snippet + "</p>"

    # Build snippet window
    start = max(0, best_idx - 50)
    end = min(len(text), best_idx + len(best_word) + 50)

    # Adjust start to nearest word boundary
    while start > 0 and text[start] not in (" ", "\n", "\t"):
        start -= 1

    # Add one extra if beginning starts on a space
    if(text[start] == " "):
        start += 1

    # Adjust end to nearest word boundary
    while end < len(text) and text[end] not in (" ", "\n", "\t"):
        end += 1

    snippet = text[start:end]

    # Bold all query words (case-insensitive)
    for w in words:
        snippet = re.sub(
            rf"({re.escape(w)})",
            r"<b>\1</b>",
            snippet,
            flags=re.IGNORECASE
        )

    # Snippet Design
    if start != 0:
        if(start-40 > 0):
            final_snippet += "..."
            final_snippet += text[start-40: start]
        else:
            final_snippet += text[0:start]
    final_snippet += f'<span style="color: black; background-color: yellow;">{snippet}</span>'
    if end != len(text):
        final_snippet += text[end:end+40]
        if(end+40 < len(text)):
            final_snippet += "..."

    final_snippet += "</p>"

    return final_snippet

@app.template_filter("highlight")
def highlight(text, query):
    # Highlighting query words in usernames or embedded titles
    pattern = re.escape(query)
    return re.sub(
        pattern,
        lambda m: f"<span style='font-weight: bold; background-color: yellow;'>{m.group(0)}</span>",
        text,
        flags=re.IGNORECASE
    )

#Running app locally
if __name__ == "__main__":
    app.run(debug=True)

