# Project Verity

A graph-based credibility inference system for conflicting e-commerce product specifications.

# Problem

Sources frequently copy each other, causing incorrect claims to propagate across the web. Simple majority voting fails because agreement does not imply independence. Verity models the relationship between sources and claims as a graph and uses recursive analysis to estimate the credibility of every source and the confidence of every claim it asserts.

# Core Challenge

Each source asserts claims about product attributes, but source credibility and claim credibility depend on each other recursively.
A source becomes credible if it consistently supports true claims.
A claim is credible if it is supported by credible sources.

# Approach

Sources and claims form a bipartite graph. Each edge represents a source asserting a claim about a product spec. Rather than resolving conflicts by majority vote, Verity jointly infers source credibility and claim confidence from the graph.
The idea is to see whether credibility can emerge naturally through repeated movement across the network.

You can think of it as a verifier travelling through the network at random: starting on one source then moving to it's set of claims it asserts, then from those claims to it's other supporting sources, over and over again. Sources that consistently connect to credible claims you'll end up on more often. Claims supported by credible sources also get revisited more often.

# Stack

- Python (crawler + scraper)
- SQLite (data storage)

# Current Status of Verity

- Prototype in development
- Retailer, manufacturer, and government source ingestion
- Approximately 275-300 products indexed
- Sources include Amazon, Walmart, Target, Best Buy, Home Depot, Apple and more
- 15,000+ extracted claims (soon to be many more!)
