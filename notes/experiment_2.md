# Experiment 2 - Initialization Stability

Date: June 10, 2026

## Setup

Sources: 24

Claims: 15,185

Initialization A:

All source credibility scores initialized uniformly.

Initialization B:

All source credibility scores initialized randomly and then normalized.

Update Rule:

Claim support = sum(source credibility)

Source credibility = average(claim support)

Repeated for 20 iterations.

## Results

Top Sources (Uniform Initialization)

1. jbl.com .............. 0.163609
2. belkin.com ........... 0.114268
3. bhphotovideo.com ..... 0.091313

Top Sources (Random Initialization)

1. jbl.com .............. 0.164408
2. belkin.com ........... 0.114557
3. bhphotovideo.com ..... 0.091614

Maximum difference between any source score:

0.0007991152

The ordering of the highest-ranked sources remained unchanged.

## Observations

I have noticed the algorithm produced nearly identical credibility distributions despite starting from different initial conditions.

The highest-ranked sources remained the same and all final credibility scores differed only slightly.

This suggests that the propagation process is largely determined by graph structure instead of the initial assignment of credibility scores.

In this dataset, credibility appears to converge toward a stable ranking after repeated propagation through the source-claim network.

## Interpretation

One concern with recursive credibility systems is that the final ranking may depend heavily on arbitrary starting values.

This experiment provides preliminary evidence that the current propagation rule may be relatively insensitive to initialization.

If this behavior persists under additional testing, the resulting credibility distribution may represent a property of the graph itself.

## Questions

* Does the same behavior occur across many random initializations?
* How quickly does the system converge?
* How does degree normalization affect the final ranking?
* Does the maximum difference continue shrinking with additional iterations?
* Is there a unique fixed point for this propagation rule?