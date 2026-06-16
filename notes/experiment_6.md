# Experiment 6 - Unique Claim Collapse

Date: June 16, 2026

I noticed something strange after looking at the final source rankings. Several sources consistently converged to exactly zero credibility:

- lenovo.com
- pcrichard.com
- hp.com
- macys.com
- cosori.com
- dell.com
- bjs.com

I suspected a bug is present in the propagation algorithm because zero is a bit random.
However after computing claim support after the graph, a pattern became visible.

For each source, I computed:

unique_ratio =
(unique claims asserted by source) /
(total claims asserted by source)

where a unique claim is asserted by exactly one source.

Interesting result:

```text
lenovo.com      57 / 57 unique claims   (1.0000)
pcrichard.com   50 / 50 unique claims   (1.0000)
hp.com          47 / 47 unique claims   (1.0000)
macys.com       23 / 23 unique claims   (1.0000)
cosori.com      12 / 12 unique claims   (1.0000)
dell.com        12 / 12 unique claims   (1.0000)
bjs.com         10 / 10 unique claims   (1.0000)
```
Meanwhile:
```
ninjakitchen.com   14 / 25 unique claims    (0.5600)
jbl.com            28 / 42 unique claims    (0.6667)
microcenter.com   511 / 690 unique claims   (0.7406)
amazon.com       2526 / 3019 unique claims  (0.8367)
bestbuy.com      4615 / 5276 unique claims  (0.8747)
```

Every source that collapsed to zero had a unique ratio of exactly 1.0.

To see whether this pattern extended beyond only the collapsed sources, I plotted each source's unique claim ratio against its final credibility score:

![Isolation vs credibility](../images/isolation_vs_credibility.png)

Interestingly enough, the relationship does not appear purely linear. Several highly credible sources still accumulate high unique claim ratios. Though, every source with a unique ratio of exactly 1.0 converged to zero credibility.

Why?

At least on the current graph, it appears as though unsupported claims may simply just not have enough paths to receive credibility back.

source -> claim -> source

This raises an important question we have to confront. Is the system penalizing false claims, or merely isolated ones?

After all- a unique claim is not always necessarily incorrect. It may simply be new information that no other source has observed and recorded yet.

Likewise, agreement is not necessarily evidence of truth. Multiple sources may be repeating the same incorrect information.

This suggests there may be at least four possible cases:

- shared truth
- shared falsehood
- unique truth
- unique falsehood

The graph currently observes agreement. It does not account for independence yet.

Suppose a source is notorious for copying another source. How do we know? How does the system naturally identify correlated sources and ultimately, the outlier(s)?