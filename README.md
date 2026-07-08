# Project Verity

A graph-based credibility inference system for networks of conflicting claims. Verity models sources and claims as a bipartite graph to infer the credibility of every source and claim.

# Problem

As artificial intelligence systems and autonomous agents reason and execute complex tasks across digital environments using information collected from many sources, evaluating the credibility of information becomes highly important.

# Research Challenge

Source credibility and claim credibility depend on each other recursively.

A source becomes more credible if it consistently supports true claims.
A claim becomes more credible if it is supported by credible sources.

When an agent scrapes data from 50 different websites, how do we know who to trust?

We typically rely on agreement between sources as evidence of truth. But, if Source A and Source B agree, is it really agreement? Or did Source B just scrape and copy its data from Source A?

# Approach

Sources and claims form a bipartite graph. Each edge represents a source asserting a claim. Verity models information as an interconnected network instead of a collection of independent observations.
<p align="center">
  <img src="images/credibility_animation.gif" width="520">
</p>

<p align="center">
  <em>An animation of credibility propagation running on a small network of sources and claims. Node size represents inferred credibility, while edges represent assertions.</em>
</p>

Credibility is computed iteratively across the graph. At each iteration step, each source distributes its credibility across all claims it asserts, and each claim in turn redistributes the support it has accumulated back to the asserting sources. The iterations repeat until the credibility vector reaches a fixed point. Agreement weighting influences how much support each assertion contributes.

# Content-Agnostic Core

Verity does not interpret a claim's content. The current implementation uses product specifications as a development dataset because they provide large-scale conflicting information from independent sources. In production, clients construct their own credibility graphs from any domain.

Verity operates purely on graph structure and receives only source identifiers, claim identifiers, and the assertion relationships between them. This means graphs have already been parsed, normalized, deduplicated, canonicalized, and otherwise pre-processed before they are ingested by Verity.

For instance, a client application could identify the following as equivalent assertions of one claim:

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
  
## Current Status of Verity

Verity is an active research project exploring how source credibility can be inferred solely from graph structure.

Currently present in the repository:

- Credibility propagation algorithm reference implementation
- Research paper with figures
- Experimental MCP interface
- Graph structure example
- Sketches of initial design

Current research focuses on modeling source dependencies to ensure that copied information contributes less evidence than independent agreement.

## AI Integration

Verity explores how graph-based source credibility inference can become accessible to autonomous AI systems.

Modern AI agents are capable of retrieving vast amounts of information at scale, but still lack a native mechanism for reasoning about the credibility of information. This becomes problematic as these agents become integrated into everyday decision-making and act on information on behalf of users.

The goal is to expose the Verity inference engine through an open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server so that AI agents can incorporate credibility inference directly into their reasoning process.
