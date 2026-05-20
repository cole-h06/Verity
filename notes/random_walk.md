# Random Walk Notes

Can credibility emerge naturally from repeated movement across a graph of sources and claims?

Suppose a source supports one or more claims. Those claims are also supported by other sources, which then support other claims, and so on.

What parts of the network does the process keep returning to over time?

The structure can be represented as a bipartite graph:

<p align="center">
  <img src="../images/source_claim_graph.png" width="370">
</p>

\[
G = (S, C, E)
\]

Where:
- \(S\) represents sources
- \(C\) represents claims
- \(E\) represents assertions between them

One possible traversal process:

- source -> claim
- claim -> supporting source
- repeat

Maybe some regions of the graph reinforce themselves more strongly than others.

Right now I'm experimenting with recursive update ideas like:

\[
c_j = \sum_i w_i A_{ij}
\]

\[
w_i^{(t+1)} \propto \sum_j c_j A_{ij}
\]

where claims reinforce sources and sources reinforce claims.

Another problem is the walk can get trapped (e.g. "Claim Echo Loops" where two sources copy each other's specifications) or hit dead ends (e.g. a claim appears on a single obscure source).

It is important to note that agreement clearly does not imply independence. If many sources are all indirectly copying the same upstream information, the graph can appear highly confident with a lack of independent verification. In such a case, majority voting feels misleading.

Perhaps introducing a small random jump probability helps prevent this to ensure full distribution:

\[
P' = \alpha P + (1-\alpha)U
\]
