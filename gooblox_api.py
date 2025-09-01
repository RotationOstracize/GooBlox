"""
GooBlox API
-----------

This module implements a simple web API that exposes search functionality
similar to Google using the `duckduckgo-search` library.  DuckDuckGo’s search
engine is privacy‑focused and offers a more permissive alternative to Google’s
Custom Search JSON API, which has daily quotas and requires an API key.  The
API defined here is deliberately lightweight so it can be hosted on common
platforms such as Replit, Railway, Render or a self‑hosted VPS.  It returns
JSON formatted results and can be integrated into Roblox games or other
applications.

Why DuckDuckGo instead of Google?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Google’s terms of service prohibit automated scraping of their search results
without explicit permission【94872066728442†L29-L34】, and the official Custom Search JSON
API only provides 100 free queries per day【511659069481057†L126-L133】.  In contrast,
`duckduckgo_search` is an open source library that fetches DuckDuckGo search
results and returns them as a list of dictionaries【7990937418174†L351-L374】.  Because
DuckDuckGo does not publish an official quota for casual use and the library
uses random user‑agents and rate limiting, it is better suited for hobby
projects.  If you later decide to scale, consider using a commercial SERP API.

The API exposes a single endpoint `/search` that accepts a GET request with
query string `q` and optional `max_results`, `region`, `safesearch` and
`timelimit` parameters.  It returns a JSON response containing the list of
results or an error message if no results are found.
"""

from flask import Flask, request, jsonify
from duckduckgo_search import DDGS
import os

app = Flask(__name__)

# Initialize the search engine once at startup.  You can configure a proxy
# via the environment variable DDGS_PROXY if you wish to use Tor or other
# proxies; see the library documentation【7990937418174†L282-L304】.
search_engine = DDGS()

@app.route("/search", methods=["GET"])
def search():
    """Search endpoint returning DuckDuckGo search results as JSON.

    Query parameters:
    - q:        The search query string (required).
    - max_results: Number of results to return (optional, defaults to 5).
    - region:   Search region code, e.g., "us-en" for United States (optional).
    - safesearch: "on", "moderate", or "off" (optional, defaults to "moderate").
    - timelimit: Time filter: d=day, w=week, m=month, y=year (optional).

    Returns JSON with keys:
    - query:     Echo of the input query.
    - results:   List of result dictionaries with keys "title", "href", "body".
    - count:     Number of results returned.
    - message:   Optional message when no results are found.
    - error:     Optional error description when an invalid request occurs.

    Example request:
    GET /search?q=python%20programming&max_results=3

    Example response:
    {
        "query": "python programming",
        "count": 3,
        "results": [
            {
                "title": "Python (programming language) - Wikipedia",
                "href": "https://en.wikipedia.org/wiki/Python_(programming_language)",
                "body": "Python is a high-level, general-purpose programming language. ..."
            },
            ...
        ]
    }
    """
    query = request.args.get("q")
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    # Parse optional parameters with sensible defaults
    try:
        max_results = int(request.args.get("max_results", 5))
        if max_results <= 0:
            raise ValueError
    except ValueError:
        return jsonify({"error": "max_results must be a positive integer"}), 400

    region = request.args.get("region", "us-en")
    safesearch = request.args.get("safesearch", "moderate").lower()
    timelimit = request.args.get("timelimit")  # None means no filter

    # Validate safesearch parameter
    if safesearch not in {"on", "moderate", "off"}:
        return jsonify({"error": "safesearch must be 'on', 'moderate', or 'off'"}), 400

    try:
        results = search_engine.text(
            keywords=query,
            region=region,
            safesearch=safesearch,
            timelimit=timelimit,
            max_results=max_results,
        )
    except Exception as ex:
        # Return a generic error message; in production you might log ex
        return jsonify({"error": f"Search failed: {ex}"}), 500

    if not results:
        return jsonify({
            "query": query,
            "count": 0,
            "results": [],
            "message": "No results found for the given query."
        }), 200

    return jsonify({
        "query": query,
        "count": len(results),
        "results": results
    })


def run():
    """Run the Flask development server.

    When deploying to a production environment you should use a WSGI server
    like Gunicorn or Uvicorn (for ASGI).  For example:

        gunicorn --bind 0.0.0.0:8000 gooblox_api:app

    This function is provided for convenience when testing locally.
    """
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run()
