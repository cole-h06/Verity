# Propagation Notes

Can credibility emerge naturally from repeated propagation across a graph of sources and claims?

Suppose a source asserts one or more claims. Those claims are also asserted by other sources, which then assert other claims, and so on. These "assertions" create a connection between a source and a claim.

Can stable credibility be assigned purely from the graph structure alone?

The structure can be represented as a bipartite graph:

<p align="center">
  <img src="../images/credibility_graph2.png" width="600">
</p>

$$
G = (S, C, E)
$$

where S is the set of sources, C is the set of claims, and E is the set of
assertions which connect sources to the claims they assert.

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

A problem with this though is that propagation can get trapped (e.g., "Claim Echo Loops" where sources copy each other's claims) or hit dead ends (e.g., a claim appears on a single obscure source).

It is also important to note that agreement clearly does not imply independence. As said before, many sources may be copying, or, "scraping" the same misleading upstream information which results in the graph appearing highly confident despite a lack of independent verification.
