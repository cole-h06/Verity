# Experiment 4 - Fixed Point Convergence

Date: June 13, 2026

Current graph:

* 24 sources
* 12,783 claims
* 13,962 assertions

![Graph summary](../images/exp4_graph_summary.png)

*Current graph size and early convergence under uniform initialization.*

Current propagation:

```text
source -> claim -> source
```

We allow for each source to distribute its credibility across all claims it asserts.

The sequential process as is:

Claim support:

$$
c_j = \sum_i \frac{s_i}{d_i}
$$

where:

* (s_i) = source credibility
* (d_i) = number of claims made by source (i)

Then claims vote back onto sources:

$$
s_i' = \frac{1}{|C_i|}\sum_j c_j
$$

After each iteration we normalize:

$$
\sum_i s_i = 1
$$

Convergence metric:

$$
\Delta = \max_i |s_i^{(t+1)} - s_i^{(t)}|
$$

Ran two initializations:

* uniform
* random

Uniform converged after 97 iterations.

![Random initialization](../images/exp4_random_start.png)

*Early iterations under random initialization begin from a different starting distribution.*

Random converged after 94 iterations.

![Random convergence](../images/exp4_random_convergence.png)

*Uniform initialization converged after 97 iterations.*

Final difference between solutions:

```text
2.37e-8
```

![Solution difference](../images/exp4_solution_difference.png)

*The final solutions differ by only 2.37 × 10^-8.*

So at the moment it looks like we're converging to essentially the same fixed point regardless of initialization.

Unexpected result:

```text
bjs.com ≈ 0.99999996
```

while nearly every other source collapses toward zero.

![Final rankings](../images/exp4_final_rankings.png)
![Final rankings](../images/exp4_solution_difference.png)

*Final source credibility scores after convergence.*

Need to figure out whether this is graph structure, source degree effects, duplicate information reinforcing itself, missing disagreement propagation, or, perhaps, just something wrong in the operator itself...

Also, still haven't incorporated explicit disagreement yet. Currently, agreement only adds support. Conflicting claims don't directly subtract credibility.

Next steps:

* claim-level disagreement
* damping or "teleportation"
* random walks directly on the bipartite graph
* product-scoped exclusivity
