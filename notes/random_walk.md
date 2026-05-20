# Random Walk Intuition

Can credibility emerge naturally from repeated movement across a graph of sources and claims?

Suppose a source supports one or more claims. Those claims are also supported by other sources, which then support other claims, and so on.

What parts of the network does the process keep returning to over time?

The structure can be represented as a bipartite graph:

<p align="center">
  <img src="../images/source_claim_graph.png" width="320">
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

I'm not fully sure yet whether revisit frequency meaningfully corresponds to credibility, but the intuition feels interesting. Also, it is important to note that agreement clearly does not imply independence.

If many sources are all indirectly copying the same upstream information, the graph can appear highly confident with a lack of independent verification. In such a case, naive majority voting feels misleading.

Right now I'm experimenting with recursive update ideas like:

\[
c_j = \sum_i w_i A_{ij}
\]

\[
w_i^{(t+1)} \propto \sum_j c_j A_{ij}
\]

where claims reinforce sources and sources reinforce claims.

Another problem is the walk can get trapped in infinite closed loops which risks artificially inflating perceived credibility.

Maybe introducing a small random jump probability helps prevent this to ensure full distribution:

\[
P' = \alpha P + (1-\alpha)U
\]

This is loosely inspired by the intuition behind PageRank-style random walks, where occasional jumps prevent the process from becoming trapped.

Currently still exploring whether stable credibility can emerge from the graph structure itself.
