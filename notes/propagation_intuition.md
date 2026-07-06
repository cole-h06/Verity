# Random Walk Notes

Can credibility emerge naturally from repeated movement across a graph of sources and claims?

Suppose a source supports one or more claims. Those claims are also supported by other sources, which then support other claims, and so on.

What parts of the network does the process keep returning to over time?

The structure can be represented as a bipartite graph:

<p align="center">
  <img src="../images/source_claim_graph.png" width="600">
</p>

$$
G = (S, C, E)
$$

Where:
* $S$ = sources
* $C$ = claims
* $E$ = assertions

One possible traversal process:

- source -> claim
- claim -> supporting source
- repeat

Maybe some regions of the graph reinforce themselves more strongly than others.

I'm currently experimenting with recursive update ideas like:

$$
c_j = \sum_i w_i A_{ij}
$$

$$
w_i^{(t+1)} \propto \sum_j c_j A_{ij}
$$

where claims reinforce sources and sources reinforce claims.

A problem with this though is the walk can get trapped (e.g., "Claim Echo Loops" where sources copy each other's claims) or hit dead ends (e.g., a claim appears on a single obscure source).

It is also important to note that agreement clearly does not imply independence. As said before, many sources are all copying, or, "scraping" the same misleading upstream information which results in the graph appearing highly confident despite a lack of independent verification.
