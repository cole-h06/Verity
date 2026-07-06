# Propagation Notes

Can credibility emerge naturally from repeated propagation across a graph of sources and claims?

Suppose a source supports one or more claims. Those claims are also supported by other sources, which then support other claims, and so on.

Can stable credibility be assigned purely from the graph structure alone?

The structure can be represented as a bipartite graph:

<p align="center">
  <img src="../images/credibility_graph2.png" width="600">
</p>

$$
G = (S, C, E)
$$

One iteration of propagation can be defined as:

- sources distribute credibility to claims
- claims redistribute support to sources
- repeat until convergence

Some regions of the graph may reinforce themselves more strongly than others.

I'm currently experimenting with recursive update ideas like:

$$
c_j = \sum_i w_i A_{ij}
$$

$$
w_i^{(t+1)} \propto \sum_j c_j A_{ij}
$$

where claims reinforce sources and sources reinforce claims.

A problem with this though is the walk can get trapped (e.g., "Claim Echo Loops" where sources copy each other's claims) or hit dead ends (e.g., a claim appears on a single obscure source).

It is also important to note that agreement clearly does not imply independence. As said before, many sources may be copying, or, "scraping" the same misleading upstream information which results in the graph appearing highly confident despite a lack of independent verification.
