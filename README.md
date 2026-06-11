# Project Verity

A graph-based credibility inference system for networks of conflicting claims. Verity models the relationship between sources and claims as a graph to estimate the credibility of every source and the confidence of every claim it asserts.

# Problem

As AI systems make decisions and complete tasks autonomously using information gathered from across the web, evaluating the credibility of information becomes increasingly important.

# Core Challenge

Source credibility and claim credibility depend on each other recursively.

A source becomes credible if it consistently supports true claims.
A claim becomes credible if it is supported by credible sources.

# Approach

Sources and claims form a bipartite graph. Each edge represents a source asserting a claim. Verity treats information as a network rather than a collection of independent observations.
<p align="center">
  <img src="images/credibility_animation.gif" width="520">
</p>

<p align="center">
  <em>An animation of credibility propagation running on a small network of sources and claims. Node size represents inferred credibility, while edges represent assertions.</em>
</p>
The idea is to see whether credibility can emerge naturally through repeated movement across the graph.

You can think of it as a verifier traveling at random: starting on one source then moving to the set of claims it asserts, then from those claims to it's other supporting sources, over and over again. Sources that consistently connect to credible claims will get revisited more often. Claims supported by credible sources also get revisited more often.

The current implementation focuses on product specifications as an initial testbed. However, the underlying framework is not specific to e-commerce. Any domain involving sources, claims, and disagreement can potentially be modeled using the same graph structure.

# Stack

- Python (crawler + scraper)
- SQLite (data storage)

## Current Status of Verity

(As of June 10, 2026)

### Dataset

- 24 sources
- 15,185 canonical claims

### Recent Results

- Ran the first credibility propagation experiment
- Non-uniform rankings emerged from a uniform starting state
- Tested random initialization
- Rankings were nearly identical after convergence
- Maximum observed difference: 0.000799

### Open Questions

- Should source degree be normalized?
- How should source independence be modeled?
- Does the system always converge to the same ranking?
- Can agreement be separated from correctness?
- Can credibility emerge from graph structure alone?
