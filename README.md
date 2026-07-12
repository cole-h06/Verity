# Verity

A graph-based credibility inference engine for information networks. Verity models sources and claims as a bipartite graph to infer the credibility of every source and claim.

# Problem

As AI systems, from foundational large language models (LLMs) to fully autonomous agents, reason and execute complex tasks across digital environments using information collected from many sources, evaluating the credibility of this information becomes highly important.

# Research Challenge

Source credibility and claim credibility depend on each other recursively.

A source becomes more credible if it consistently supports true claims.
A claim becomes more credible if it is supported by credible sources.

When an agent scrapes data from 50 different websites, how do we know who to trust?

We typically rely on agreement between sources as evidence of truth. But, if Source A and Source B agree, is it really agreement? Or did Source B just copy its data from Source A?

# Approach

Sources and claims form a bipartite graph. Each edge represents a source asserting a claim. Verity models information as an interconnected network instead of a collection of independent observations.
<p align="center">
  <img src="images/credibility_animation.gif" width="520">
</p>

<p align="center">
  <em>An animation of credibility propagation running on a small network of sources and claims. Node size represents inferred credibility, while edges represent assertions.</em>
</p>

Credibility is computed iteratively across the graph. At each iteration step, each source distributes its credibility across all claims it asserts, and each claim in turn redistributes the support it has accumulated back to the asserting sources. The iterations repeat until the credibility vector reaches a fixed point. Agreement weighting influences how much support each assertion contributes.

# Domain-Agnostic Design

Verity does not interpret a claim's content. The current implementation uses product specifications as a development dataset because they provide large-scale conflicting information from independent sources. In production, clients construct their own credibility graphs from any domain.

Verity operates purely on graph structure. The engine only receives unique identifiers that correspond to sources, claims, and the assertions between them. This means graphs have already been parsed, normalized, deduplicated, canonicalized, and otherwise pre-processed before they are ingested by Verity.

Some examples where a client application could merge equivalent assertions before constructing a credibility graph include:

```text
Product specifications:

- Bluetooth 5.3
- BT 5.3
- Version 5.3

AI coding agents:

- Python 3.12
- Python 3.12.0
- Python v3.12

Enterprise knowledge:

- Financial Report -> Revenue: $4.2M
- ERP Export -> Revenue = 4,200,000 USD
- Slack Discussion -> Quarterly revenue was $4.2 million
```

# Stack

- Python
- PostgreSQL

# Repository

- `benchmark/` — Reproducible benchmark dataset
- `credibility/` — Credibility inference engine
- `experiments/` — Experimental algorithms and research prototypes
- `mcp/` — Experimental MCP server
- `paper/` — Research paper
- `research/` — Research notes
  
# Current Status

Verity is an active research project focused on evaluating source credibility based on the graph structure of an information network.

Main area of research currently is [modeling source dependencies](research/source_dependencies.md) to ensure that copied information contributes less evidence than independent agreement.

# Vision

Verity explores how credibility inference can be made accessible and simplified for AI systems.

Modern autonomous agents are capable of retrieving vast amounts of information at scale, but still lack a native mechanism for reasoning about the underlying credibility of information. This becomes problematic as these agents become integrated into everyday decision making and act on information on behalf of users. Current methods for evaluating information primarily analyze what was said. While LLMs are capable of reasoning about semantic text and supporting evidence, their ability to reason about the structure of information itself is limited.

Verity takes a different approach by modeling information as a bipartite graph of source-to-claim assertions. It evaluates the topology of an information network and shifts credibility inference from reasoning about what was said to reasoning about who knows whom.

The mission is to make the Verity credibility inference engine accessible through an open-source [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server that allows AI systems to seamlessly incorporate credibility inference directly into their reasoning process.

# Contact

Feel free to connect with me whether you have any ideas, questions, feedback, or if you just want to chat about interesting topics! 

Email: colehoke1@gmail.com

LinkedIn:
https://www.linkedin.com/in/cole-hoke-8537002a2/
