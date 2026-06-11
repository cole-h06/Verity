# Experiment 3 - Degree Normalization

Date: June 10, 2026

## Question

One potential problem with the initial propagation model is that sources asserting many claims may accumulate an advantage simply because they participate in more parts of the graph.

To test this, source credibility was divided by source degree before being distributed to claims.

The goal was to determine whether the rankings produced by Experiment 1 were primarily driven by graph structure or by source claim volume.

## Setup

Sources: 24

Claims: 15,185

Initialization A:

All sources initialized uniformly.

Initialization B:

Random source credibility distribution.

Update Rule:

Claim support = sum(source credibility / source degree)

Source credibility = average(claim support)

Repeated for 20 iterations.

## Results

### Uniform Initialization

1. bjs.com .............. 0.814721
2. cosori.com ........... 0.185014
3. amazon.com ........... 0.000204
4. belkin.com ........... 0.000057

All remaining sources received effectively zero credibility.

### Random Initialization

1. bjs.com .............. 0.886246
2. cosori.com ........... 0.113401
3. amazon.com ........... 0.000222
4. belkin.com ........... 0.000125

All remaining sources received effectively zero credibility.

Maximum difference between any source score:

0.0716127598

## Comparison to Experiment 2

Experiment 2 produced a relatively stable distribution.

Top-ranked sources remained unchanged between uniform and random initialization, and the maximum observed difference was:

0.0007991152

After introducing degree normalization, the system became substantially more sensitive to initialization.

Maximum observed difference increased to:

0.0716127598

This represents nearly two orders of magnitude more variation than the previous experiment.

## Observations

The resulting credibility distribution became extremely concentrated.

Nearly all credibility accumulated in two sources:

* bjs.com
* cosori.com

Most other sources received effectively zero credibility after convergence.

This behavior was not observed in Experiment 1 or Experiment 2.

The degree-normalized system also became significantly more sensitive to initialization.

## Interpretation

The normalization procedure appears to over-correct for source size.

I divided credibility by source degree before propagation which resulted in large sources being heavily penalized while small highly-connected portions of the graph receive disproportionate influence.

The resulting rankings appear less stable and less distributed than those produced by the original propagation rule.

This suggests that naive degree normalization may distort the propagation process rather than improve it.

## Open Questions

* Is source degree the correct quantity to normalize by?
* Should normalization occur on the source side, the claim side, or both?
* Is the current update rule effectively penalizing source degree twice?
* Why do bjs.com and cosori.com dominate after normalization?
* Can degree effects be controlled without collapsing credibility into a small number of sources?
* Is there a normalization scheme that preserves stability while reducing degree bias?

## Conclusion

The initial propagation model appears substantially more stable than the naive degree-normalized variant tested here.

While I think degree bias remains an open concern, simple source-degree normalization produced highly concentrated rankings and increased sensitivity to initialization.

Additional normalization strategies will be required before drawing conclusions about the role of source degree in the credibility propagation process.