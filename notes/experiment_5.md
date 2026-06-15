# Experiment 5 - Bidirectional Normalization

**Date:** June 14, 2026

Experiment 4 showed that the graph consistently converges to a fixed point under both uniform and random initialization.

Noted that the resulting rankings revealed a problem. Even after source degree normalization, some sources could still accumulate nearly all credibility because of the graph structure.

To address this, we introduced normalization on both sides of the bipartite graph.

## Previous propagation

The original propagation step allows for distribution of source credibility across the claims asserted by each source:

$$
q_j = \sum_i \frac{s_i}{d_i}
$$

where:

* $(s_i)$ = source credibility

* $(d_i)$ = number of claims made by source $(i)$

The claims then vote back onto sources:

$$
s_i' = \frac{1}{|C_i|}\sum_j q_j
$$

After each iteration we normalize:

$$
\sum_i s_i = 1
$$

## Bidirectional normalization

In v4 we additionally normalize claim support by the number of supporting sources:

$$
q_j = \frac{1}{|S_j|}\sum_i \frac{s_i}{d_i}
$$

where:

* $(|S_j|)$ = number of sources asserting claim $(j)$

The idea is simple: if many sources contribute to the same claim, we average that support instead of allowing it to accumulate indefinitely.

## Current graph

* 24 sources

* 12,684 claims

* 13,860 assertions

Average sources per claim:

$$
1.09
$$

Average sources per product:

$$
2.02
$$

Products by number of sources:

* 155 products with 1 source

* 77 products with 2 sources

* 56 products with 3 sources

* 29 products with 4 sources

* 13 products with 5 sources

* 2 products with 6 sources

## Results

Both initialization schemes converged:

* Uniform initialization: 81 iterations

* Random initialization: 90 iterations

Maximum difference between final solutions:

$$
4.44 \times 10^{-8}
$$

The resulting rankings were substantially more balanced than in previous experiments.

Top sources:

1. bestbuy.com — 0.328
2. amazon.com — 0.231
3. target.com — 0.120
4. microcenter.com — 0.097
5. bhphotovideo.com — 0.084

## Current observations

The algorithm now appears to behave much more reasonably than in earlier experiments. The remaining limitation is not convergence, but graph density.

Most claims are still asserted by only a single source:

$$
\text{Average sources per claim} \approx 1.09
$$

This means the graph contains relatively little agreement information for credibility propagation.

Going forward, improving product matching and claim canonicalization may have a larger impact than further changes to the propagation algorithm itself.

The current results suggest that the propagation scheme is no longer the primary bottleneck. Instead, I believe increasing overlap between sources may provide the largest improvement going forward in future experiments.
