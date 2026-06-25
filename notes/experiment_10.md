# Experiment 10 - Agreement-Weighted Propagation

Date: June 24, 2026

## Motivation

The previous propagation algorithm assigned equal influence to each assertion. When a source asserted a claim, its credibility contribution was distributed uniformly among all outgoing assertions regardless of if the asserted value agreed with or contradicted competing sources.

This experiment modifies the approach by using an agreement-weighted propagation method. Assertions that agree with a larger proportion of competing sources receive greater influence when spread during propagation, whereas those that are part of a minority will contribute proportionally less support.

The objective here is to determine if the local agreement information can be introduced without compromising the overall convergence toward a final, stable credibility vector.

## Method

First, for each `(product_id, canonical_attribute)` pair, assertions were grouped based on their values after deterministic canonicalization is applied. 

Then, each assertion received an agreement weight defined as:

$$
w =
\frac{\text{number of sources asserting the same value}}
{\text{number of sources asserting the attribute}}
$$


In each iteration, the credibility was propagated to claim nodes through these agreement-weighted assertion edges. The resulting claim support values were then propagated back to the source nodes before the credibility vector was normalized.

All other propagation rules from previous experiments were kept the same.

The following tests were run:

1.  Uniform initialization using weighted agreement.

2.  Uniform initialization using unweighted assertion edges.

3.  Random initialization using weighted agreement.

## Results

### Convergence

The agreement-weighted propagation converged after **37 iterations**.

![Agreement-weighted convergence (early iterations)](../images/exp10_convergence_start.png)

*Agreement-weighted convergence (early iterations)*

The credibility vector initially changed rapidly as credibility propagated throughout the graph.

![Agreement-weighted convergence (final iterations)](../images/exp10_convergence_end.png)

*Agreement-weighted convergence (final iterations)*

We can observe above the maximum change between successive iterations of the credibility vector consistently dropped and was within the defined threshold.

### Agreement Effects

The credibility standings determined from agreement-weighted propagation were contrasted against a scenario utilizing an otherwise identical propagation algorithm, except that assertions had a standard weight of 1.0 regardless of consensus.

![Largest agreement effects](../images/exp10_agreement_effects.png)

*Largest agreement effects*

We can see that agreement weights resulted in noticeable differences in the final rankings. Best Buy increased most in credibility, whereas Micro Center and B&H Photo Video decreased furthest. The overall ranks largely held their ground, with other sources showing minimal shifts.

### Initialization Independence

I repeated the experiment using random initial credibility scores.

Both methods of initialization resulted in almost nearly identical final convergence. This implies agreement-weighted propagation retains previous initial convergence properties.

## Observations

This experiment shows that agreement information can be incorporated directly into the credibility propagation process while preserving stable convergence.

The agreement-weighting model caused measurable changes in the final rankings, but without affecting the basic dynamic behavior of the iterative algorithm. I noted that sources that more frequently agreed with competing sources received relatively modest increases in credibility, and conversely, sources that more frequently disagreed experienced corresponding decreases.

These changes were expected given the current state of the dataset. Agreement weights are currently computed only for attributes that support deterministic canonicalization, limiting the proportion of the graph that participates in weighted propagation.

Going forward, with further attribute normalization, I expect a larger portion of the graph will receive agreement weights, thereby allowing future experiments to evaluate their influence across a broader range of product properties.

## Current Limitations

Agreement weighting can only be applied to attributes with deterministic canonicalization rules.

There are currently many attributes that still contain inconsistent textual representations that we cannot yet normalize automatically. Assertions involving these attributes currently receive the default edge weight and therefore do not contribute agreement information. Future work will expand normalization coverage while keeping the underlying propagation algorithm unchanged.
