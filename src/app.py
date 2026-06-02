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
    
    #TODO: the ranking part aka B2; interface has been done (very simple). Look at B2 in CS172 project for details
    #Use elasticsearch 
    results = [] #List of results 




    return render_template("results.html", query=query, results=results)
    
        

#Running app locally
if __name__ == "__main__":
    app.run(debug=True)

