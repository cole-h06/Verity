# Project Verity

A credibility inference system for networks of conflicting claims. Verity models the relationship between sources and claims as a graph to estimate the credibility of every source and the confidence of every claim it asserts.

# Problem

As AI systems and autonomous agents make decisions and execute complex tasks using information gathered from across the web, evaluating the credibility of information becomes increasingly important.

# Core Challenge

Source credibility and claim credibility depend on each other recursively.

A source becomes credible if it consistently supports true claims.
A claim becomes credible if it is supported by credible sources.

Without external ground truth, we often rely on agreement between sources as evidence of truth.

However, agreement is only evidence if the sources are independent. If sources copy one another, is it really agreement? Or is it just representing a single observation?

# Approach

Sources and claims form a bipartite graph. Each edge represents a source asserting a claim. Verity treats information as an interconnected network rather than a collection of independent observations.
<p align="center">
  <img src="images/credibility_animation.gif" width="520">
</p>

<p align="center">
  <em>An animation of credibility propagation running on a small network of sources and claims. Node size represents inferred credibility, while edges represent assertions.</em>
</p>
The idea is to see whether credibility can emerge naturally through repeated movement across the graph.

One way you can think of it is a verifier traveling through the network at random: starting on one source then moving to the set of claims it asserts, then from those claims to its other supporting sources, over and over again. Sources that consistently connect to credible claims will get revisited more often. Claims supported by credible sources also get revisited more often.

# Content-Agnostic Core

Verity does not interpret the strings or meaning of claims. The current implementation uses product specifications as a development dataset because they provide large-scale conflicting information from independent sources. In production, clients construct their own credibility graphs from any domain.

Verity operates purely on the graph structure to compute source credibility, receiving only source identifiers, claim identifiers, and the assertion relationships between them. This means the graph has already been parsed, normalized, deduplicated, canonicalized, and otherwise pre-processed before it is received by Verity.

For example, a client application may determine that:

Product specifications
----------------------
Bluetooth 5.3
BT 5.3
Version 5.3

AI coding agents
----------------
Python 3.12
Python v3.12
CPython 3.12

Medical knowledge
-----------------
Myocardial infarction
Heart attack
Acute MI

all represent the same underlying claim.

# Stack

- Python
- PostgreSQL

## Current Status of Verity
(As of June 22, 2026)

## Dataset

- 24 sources
- 2,976 source claims (individual assertions collected from sources)
- 1,662 canonical claims (normalized claim nodes used in graph experiments)

## Recent Progress

- Built the first experimental credibility graph
- Built a preprocessing pipeline for graph experiments
- Measured source overlap across the graph
- Measured agreement and disagreement between sources
- Reduced claim fragmentation in the experimental dataset
- Identified isolated sources and sparsity issues
- Established a repeatable graph-building pipeline for experiments

## Open Questions

- How should agreement affect credibility?
- How should disagreement affect credibility?
- How should source copying be handled?
- How much overlap is enough?
