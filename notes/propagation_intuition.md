# Propagation Notes

Can credibility emerge naturally from repeated propagation across a graph of sources and claims?

Let's suppose a source asserts one or more claims. Those claims are in turn asserted by some other sources, which in turn assert other claims, and so on. These "assertions" create a connection between a source and a claim.

We can visualize the structure as a bipartite graph:

<p align="center">
  <img src="../images/credibility_graph2.png" width="600">
</p>

One iteration of propagation can be defined as:

- sources distribute credibility to claims
- claims redistribute accumulated support back to sources
- repeat until convergence

A challenge with iterative propagation, however, is that denser regions of the graph may carry greater influence than less connected regions. This becomes problematic if it's due to copied information instead of independent agreement. Many sources may be copying the same misleading information, ultimately creating an illusion where the graph appears highly confident despite a lack of independent verification. Similarly, claims appearing on a single source receive little or no reinforcement.
