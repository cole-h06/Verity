# Project Verity

A graph-based credibility inference system for conflicting e-commerce product specifications.

# Problem

Sources frequently copy each other, causing incorrect claims to propagate across the web. Verity models the relationship between sources and claims as a graph to estimate the credibility of every source and the confidence of every claim it asserts.

# Core Challenge

Source credibility and claim credibility depend on each other recursively.

A source becomes credible if it consistently supports true claims.
A claim becomes credible if it is supported by credible sources.

# Approach

Sources and claims form a bipartite graph. Each edge represents a source asserting a claim about a product spec. Rather than resolving conflicts by majority vote, Verity jointly infers source credibility and claim confidence from the graph.
<p align="center">
  <img src="images/source_claim_graph.png" width="520">
</p>

<p align="center">
  <em>Sources (red) assert claims (blue). Each edge represents one assertion.</em>
</p>
The idea is to see whether credibility can emerge naturally through repeated movement across the network.

You can think of it as a verifier traveling through the network at random: starting on one source then moving to the set of claims it asserts, then from those claims to it's other supporting sources, over and over again. Sources that consistently connect to credible claims will get revisited more often. Claims supported by credible sources also get revisited more often.

# Stack

- Python (crawler + scraper)
- SQLite (data storage)

# Current Status of Verity

- Prototype in development
- Retailer, manufacturer, and government source ingestion
- Approximately 275-300 products indexed
- Sources include Amazon, Walmart, Target, Best Buy, Home Depot, Apple and more
- 15,000+ extracted claims (soon to be many more!)
