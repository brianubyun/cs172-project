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
    # TODO: Allow ordering/filter by likes, reposts, time, replies, or relevance (or all) 
    #       to affect ranking (this is different from how we delcare our generic ranking algorithm)
    # TODO: Implement PageRank for posts
    # TODO: Should we show likes, reposts, timestamp, etc. in query results?

    query = request.args.get("query", "").strip()

    if not query: #No query so go back to default home page
        return render_template("index.html", title="Home Page")
    
    # Ranking function using Elasticsearch's function_score (BM25)
    # However, BM25 suffers from lack of semantic relationships between words so rankings are not that accurate
    es_query = {
        "query": {
            "function_score": {
                "query": {
                    "multi_match": {
                        "query": query,
                        # Decide what fields are relevant and weights for relevancy
                        "fields": [
                            "text^3",               # Text is weighed 3x important
                            "embedded_title^2",     # Embedded Titles are 2x important
                            "embedded_description"  # Embedded Descriptions are 1x important
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
                            "factor": 0.001,
                            "modifier": "sqrt",
                            "missing": 0
                        }
                    },
                    {
                        # Number of reposts a post has boosts score (reposts weight more)
                        "field_value_factor": {
                            "field": "reposts",
                            "factor": 0.005,
                            "modifier": "sqrt",
                            "missing": 0
                        }
                    },
                    {
                        # Number of replies a post has boosts score (replies mean engagement)
                        "field_value_factor": {
                            "field": "replies",
                            "factor": 0.01,
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
            "score": hit["_score"],
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

#Running app locally
if __name__ == "__main__":
    app.run(debug=True)

