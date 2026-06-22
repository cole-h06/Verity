# Experiment 8 - Agreement Weighted Propagation

Date: June 20, 2026

The verifier in Experiment 7 was a function of connectivity.

Disconnected components naturally collapsed to zero because they had no structural path back into the main graph.

This meant the verifier was really measuring connectivity, not agreement.

The next question was: can we include source agreement directly in the credibility propagation process?

## Measuring Agreement

We gathered all of the source assertions attached to any given canonical claim from `source_claims`.

We then measured agreement as:

```text
largest agreeing group
----------------------
total attached assertions
```

Examples:

```text
3 sources

Bluetooth 5.3
Bluetooth 5.3
Bluetooth 5.3

agreement = 1.00
```

```text
4 sources

Bluetooth 5.3
Bluetooth 5.3
Bluetooth 5.2
Bluetooth 5.2

agreement = 0.50
```

```text
3 sources

Bluetooth 5.3
Bluetooth 5.2
Bluetooth 5.1

agreement = 0.33
```

When we run this calculation over the current graph:

```text
perfect agreement claims: 1743

partial agreement claims: 8880

total claims: 10623
```

Agreement signals are clearly present throughout the graph and frequently enough to influence propagation if the graph structure allows it.

## Agreement Weighted Propagation

We adapted the propagation algorithm such that claim support is scaled by agreement:

```text
claim_support =
    structural_support
    × agreement_score
```

Where agreement_score is:

```text
agreement_score =

largest agreeing group
----------------------
total attached assertions
```

Credibility still flows:

```text
source -> claim -> source
```

but agreement now scales how much support a claim contributes back into the graph.

## Results

The verifier converged normally.

Both a uniform and random initialization converged to the same fixed point.

The top ranked sources changed only marginally.

Pre-agreement:

```text
bestbuy.com       0.3209

amazon.com        0.2044

target.com        0.1467

microcenter.com   0.1085

bhphotovideo.com  0.0928
```

Post-agreement:

```text
bestbuy.com       0.3399

amazon.com        0.1998

target.com        0.1465

microcenter.com   0.1063

bhphotovideo.com  0.0836
```

## Observation

Despite the presence of agreement signals throughout the graph, agreement-weighted propagation only altered the output credibility very slightly.

This implies that the graph structure/connectivity is still the primary driver of credibility at the moment.

This isn’t surprising given how biased the current graph’s structure is:

* Best Buy, Amazon, and Target all generate vast numbers of assertions.
* Some nodes remain totally disconnected.

These connectivity patterns appear to dominate the effect of agreement weighting.

## Conclusion

This is likely a consequence of the graph's sparsity, where relatively few claims receive support from multiple overlapping sources. This suggests the current verifier is still primarily a connectivity verifier rather than an agreement verifier. Whether agreement becomes a stronger signal on a denser, more argument-rich graph remains the next major question for the verifier.
