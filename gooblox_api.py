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
import re
from typing import Optional, Tuple


# Helper function to extract a population estimate from DuckDuckGo search snippets.
# It scans the snippet text for patterns like "600 million" or "1.2 billion".
def _extract_population_from_snippets(subject: str, results: list) -> Optional[str]:
    """Return a concise population estimate extracted from search result snippets.

    Args:
        subject: The subject of the population query (e.g. "cat", "dogs").
        results: A list of search results returned by DDGS, each with keys
            "title", "href" and "body".

    Returns:
        A formatted string describing the estimated population, or None if no
        suitable estimate is found.
    """
    # Regular expression to match numbers followed by million/billion.
    number_pattern = re.compile(r"\b([\d,]+(?:\.\d+)?\s*(?:million|billion))", re.IGNORECASE)
    # Iterate over results, prioritising bodies that mention the subject.
    for res in results:
        snippet = res.get("body", "") or ""
        # Skip if snippet does not mention the subject at all.
        if subject.lower() not in snippet.lower():
            continue
        # Find all matches of population numbers.
        matches = number_pattern.findall(snippet)
        if matches:
            # Choose the longest match (likely the largest number/range).
            # e.g., ["600 million", "1 billion"] -> choose the last.
            estimate = matches[-1]
            # Clean up the estimate (strip whitespace)
            estimate = estimate.strip()
            # Format a simple answer.
            return f"The estimated {subject} population is around {estimate}."
    # If no match found, return None
    return None

try:
    # The wikipedia library provides convenient access to Wikipedia summaries.
    import wikipedia  # type: ignore
except ImportError:
    # If wikipedia is not installed, the API will still function but no answers
    # will be generated.  In production you should add 'wikipedia' to your
    # requirements.txt to enable richer responses.
    wikipedia = None  # type: ignore

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

    # Determine the region based on the query.  By default, use English (us-en).
    region = request.args.get("region")
    if not region:
        # If the query contains non‑ASCII characters, fall back to a global region
        # to allow other languages.  Otherwise default to US English.
        region = "wt-wt" if any(ord(ch) > 127 for ch in query) else "us-en"

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

    # Build the base response
    response = {
        "query": query,
        "count": len(results),
        "results": results or [],
    }

    if not results:
        response["message"] = "No results found for the given query."
        return jsonify(response), 200

    # Attempt to generate a concise answer for common question patterns when
    # wikipedia is available.  This is best effort and will be skipped if
    # wikipedia is not installed or no summary is found.
    answer = None
    if wikipedia is not None:
        # Normalize the query for analysis
        lower_query = query.lower().strip()
        # If the query asks "what is", "who is", "define", etc.,
        # we attempt to fetch a short summary from Wikipedia.
        patterns = [
            r"^(what is|who is|define|meaning of)\s+(.+)",
            r"^(.+)\s+definition$",
        ]
        match = None
        for pattern in patterns:
            m = re.match(pattern, lower_query)
            if m:
                # The topic is in the last captured group
                topic = m.groups()[-1]
                match = topic
                break

        # Handle questions starting with "how many" or "population of"
        if not match:
            if lower_query.startswith("how many") or lower_query.startswith("population of"):
                # Extract the subject for population queries
                # e.g., "how many cats exist" -> "cats"
                subject = lower_query
                # Remove leading phrases
                for prefix in ["how many", "population of", "number of", "count of"]:
                    if subject.startswith(prefix):
                        subject = subject[len(prefix):].strip()
                # Remove common trailing words
                subject = re.sub(r"( exist| are there| are)", "", subject).strip()
                match = subject + " population"

        if match:
            try:
                # Use Wikipedia search to find the best page
                search_results = wikipedia.search(match)
                if search_results:
                    page_title = search_results[0]
                    # Fetch a concise summary (first sentence)
                    summary = wikipedia.summary(page_title, sentences=1)
                    answer = summary.strip()
            except Exception:
                # If Wikipedia search fails, ignore and proceed without answer
                answer = None

    # If we already found an answer from Wikipedia, include it.
    if answer:
        response["answer"] = answer
    else:
        # Additional heuristic: handle general population queries even when not
        # prefixed by "how many" or "population of". Correct common misspellings.
        # Work on a lowercased version of the query for analysis. Avoid using
        # lower_query from the Wikipedia block which may not exist if wikipedia
        # is None.
        lower_query_corrected = query.lower().strip()
        # Fix typical misspellings of "population"
        for misspelling in ["poplutation", "popluation", "popultation", "populaton"]:
            lower_query_corrected = lower_query_corrected.replace(misspelling, "population")
        if "population" in lower_query_corrected:
            # Extract the subject by removing leading population phrases.
            # E.g., "cat population" -> "cat", "population of cats" -> "cats".
            subject = lower_query_corrected
            for prefix in ["population of", "population for", "population in", "population"]:
                if subject.startswith(prefix):
                    subject = subject[len(prefix):].strip()
            # If we have a subject, attempt to extract numbers from search snippets.
            if subject:
                pop_answer = _extract_population_from_snippets(subject, results)
                if pop_answer:
                    response["answer"] = pop_answer

    return jsonify(response)


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
