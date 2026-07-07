# Project Verity

A credibility inference system for networks of conflicting claims. I am building Verity to see if the relationship between sources and claims can be modeled as a graph to estimate the credibility of every source and the confidence of every claim it asserts.

# Problem

As artificial intelligence systems and autonomous agents reason and execute complex tasks across digital environments using information collected from many sources, evaluating and verifying the credibility of information becomes highly important.

# Research Challenge

Source credibility and claim credibility depend on each other recursively.

A source becomes more credible if it consistently supports true claims.
A claim becomes more credible if it is supported by credible sources.

When an agent scrapes data from 50 different websites, how do we know who to trust?

We typically rely on agreement between sources as evidence of truth. But, if Source A and Source B agree, is it really agreement? Or did Source B just scrape and copy its data from Source A?

# Approach

Sources and claims form a bipartite graph. Each edge represents a source asserting a claim. Verity treats information as an interconnected network instead of a collection of independent observations.
<p align="center">
  <img src="images/credibility_animation.gif" width="520">
</p>

<p align="center">
  <em>An animation of credibility propagation running on a small network of sources and claims. Node size represents inferred credibility, while edges represent assertions.</em>
</p>

Credibility is computed iteratively across the graph. At each iteration step, each source distributes its credibility across all claims it asserts, and each claim in turn redistributes its support that it accumulated back to the asserting sources. The iterations repeat until the credibility vector reaches a steady state fixed point. Agreement weighting influences how much support each assertion contributes.

# Content-Agnostic Core

Verity does not interpret the strings or meaning of claims. The current implementation uses product specifications as a development dataset because they provide large-scale conflicting information from independent sources. In production, clients construct their own credibility graphs from any domain.

Verity operates purely on graph structure, receiving only source identifiers, claim identifiers, and the assertion relationships between them. This means the graph has already been parsed, normalized, deduplicated, canonicalized, and otherwise pre-processed before it is ingested by Verity.

For instance, a client application may determine that the following values are all equivalent assertions for the same claim:

```text
Product specifications:

- Bluetooth 5.3
- BT 5.3
- Version 5.3

AI coding agents:

- Python 3.12
- Python 3.12.0
- Python v3.12

Medical knowledge:

- Myocardial infarction
- Heart attack
- Acute MI
```

# Stack

- Python
- PostgreSQL
  
## Current Status & Implementation Notes

Verity is an active research project that aims to investigate whether source credibility can be inferred solely based on graph structure.

Currently present in the repository:

- Credibility propagation algorithm reference implementation
- Research paper with figures
- Experimental MCP interface
- Graph structure example
- Sketches of initial design

Current area of research focuses on modeling source dependencies to ensure that copied information contributes less evidence than independent agreement.
