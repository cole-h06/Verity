# Project Verity

A graph-based credibility inference system for conflicting e-commerce product specifications.

# The Problem

Product specs conflict across retailers, manufacturers, and government sites. Sources copy each other, so errors propagate. You can't resolve conflicts by majority vote alone.

# The Core Challenge

Sources and claims have a dependency relationship: a source's credibility depends on the accuracy of its claims, and a claim's accuracy depends on the credibility of its sources.

# The Approach

Sources and claims form a graph. Each edge represents a source asserting a claim about a product spec. Rather than resolving conflicts by majority vote, the goal is a scoring system where source credibility and claim confidence are inferred jointly from the structure of the graph itself.
The key question: does this graph admit a stable assignment of credibility and truth under those constraints?

# Stack

- Python (crawler + scraper)
- SQLite (data storage)
- 275-300 products scraped across multiple unique source types (soon to be many more!)

# Status

Data pipeline running. Algorithm design in progress.

