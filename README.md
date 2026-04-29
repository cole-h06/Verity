Verity

A source reliability system for e-commerce product data.

# The Problem

Product specs conflict across retailers, manufacturers, and government sites. Sources copy each other, so errors propagate. You can't resolve conflicts by majority vote alone.

# The Core Challenge

To score a claim's reliability you need to know the source's reliability. But to know the source's reliability, you need to know how accurate its claims are. It's circular.

# The Approach

Model sources and claims as a bipartite graph. Treat reliability scoring as an iterative convergence problem where source reliability scores and claim reliability scores solve each other simultaneously until they stabilize.

# Stack

- Python (crawler + scraper)
- SQLite (data storage)
- 275+ products scraped across multiple source types (retailers, manufacturers, government sites)

# Status

Data pipeline running. Algorithm design in progress.

