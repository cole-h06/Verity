# Project Verity

A graph-based credibility inference system for conflicting e-commerce product specifications.

# The Problem

Sources frequently copy each other, causing incorrect claims to propagate across the web. Simple majority voting fails because agreement does not imply independence. Verity models the relationship between sources and claims as a graph structure and uses recursive analysis to estimate credibility of every source and the confidence of every claim it asserts.

# The Core Challenge

Each source asserts claims about product attributes, but source credibility and claim credibility depend on each other recursively.
A source is credible if it consistently supports true claims.
A claim is credible if it is supported by credible sources.

# The Approach

Sources and claims form a graph. Each edge represents a source asserting a claim about a product spec. Rather than resolving conflicts by majority vote, the goal is a scoring system where source credibility and claim confidence are inferred jointly from the structure of the graph itself.
The key question: does this graph admit a stable assignment of credibility and truth under those constraints?

# Stack

- Python (crawler + scraper)
- SQLite (data storage)
- Current domains include Amazon, Walmart, Target, Best Buy, Home Depot, Lowe's
- Current categories: consumer electronics and home appliances.
- Current scale: approximately 275-300 products scraped across multiple unique source types (soon to be many more!)

# Status

Data pipeline running. Algorithm design in progress.

