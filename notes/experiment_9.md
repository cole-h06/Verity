# Experiment 9 - Agreement Weighted Propagation

Date: June 20, 2026

The verifier in Experiment 8 was a function of connectivity.

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

Agreement clearly exists in the graph - it’s not an edge case.

## Agreement Weighted Propagation

We adapted the propagation algorithm such that the credibility score a claim lends back to the graph (claim support) is now a sum:

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

We confirmed that agreement exists within the graph, but the introduction of agreement-weighted propagation only altered the output credibility very slightly.

This implies that the graph structure / connectivity is still the primary driver of credibility at the moment.

This isn’t surprising given how biased the current graph’s structure is:

* Best Buy, Amazon, and Target all generate vast numbers of assertions.
* Some nodes remain totally disconnected.

These connectivity patterns appear to dominate the effect of agreement weighting.

## Conclusion

While Experiment 8 established that connectivity plays a key role in credibility, our Experiment 9 results show that alone, agreement is not a strong enough signal in our current graph structure to overwhelm the importance of connectivity.

Although agreement is incorporated into the calculation, it is secondary to graph structure, largely because so few claims are supported by multiple overlapping sources in our current sparse dataset.

It’s possible that on a more densely populated, argument-rich graph, the agreement mechanism would show more influence; that’s the next big question for the verifier.