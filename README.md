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

One way you can think of it is a verifier traveling through the network at random: starting on one source then moving to the set of claims it asserts, then from those claims to it's other supporting sources, over and over again. Sources that consistently connect to credible claims will get revisited more often. Claims supported by credible sources also get revisited more often.

The current implementation focuses on product specifications as initial training data. However, the underlying framework is not specific to e-commerce. Any domain involving sources, claims, and disagreement can potentially be modeled using the same graph structure.

# Content-Blind Core 

Verity does not interpret the strings or meaning of claims.

Instead, the engine operates purely on the graph stucture, receiving source identifiers, claim identifiers, and the assertion relationships between them. This means the claim data has already been parsed, normalized, deduplicated, canonicalized, and otherwise pre-processed prior to being input to the graph. 

For example, a client application may determine that:

```text
Bluetooth 5.3
BT5.3
Version 5.3
```

all represent the same underlying claim.

It only sees that multiple sources asserted the same claim identifier and computes credibility from the resulting network structure.

# Stack

- Python
- SQLite

## Current Status of Verity

(As of June 14, 2026)

## Dataset

* 24 sources
* 12,684 canonical claims
* 13,860 assertions

## Recent Results

* Added bidirectional normalization to the propagation step
* Tested both uniform and random initialization
* Both initializations converged to nearly the same solution
* Maximum observed difference after convergence: 4.44e-8
* Source rankings appear much more balanced than before
* The propagation scheme now seems relatively stable
* Most claims are still asserted by only a single source

## Current Questions

* How much does increasing source overlap improve rankings?
* How should conflicting claims reduce credibility?
* How can dependence between sources be modeled?
* Is the graph still too sparse for credibility propagation?
