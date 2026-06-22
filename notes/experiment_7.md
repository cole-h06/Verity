# Experiment 7 - Canonical Claim Migration

Date: June 17, 2026

With Experiment 6, I found that nearly all (92%) of the claims were supported by a single source, indicating that claims may have been too specific, creating an overly sparse graph.

The previous definition of claim was:

```text
claim = (product_id, attribute, value)
```

With this definition, sources asserting different values for the same product attribute generated separate claim nodes.

For example:

```text
Amazon: screen_brightness = 300 nits
Best Buy: screen_brightness = 250 nits
```

Both would produce two unique claim nodes for "screen_brightness" for that product, despite relating to the same product attribute.

Therefore, we redefined claims as:

```text
claim = (productid, canonicalattribute)
```

while source-specific values remained stored in `source_claims`.

This migration also changes what a claim represents.

Under the previous schema, agreement was encoded directly into the graph because sources asserting identical values connected to the same claim node.

Under the new schema, a claim represents a product attribute regardless of the asserted value. Sources now connect through a shared claim even when they disagree. Agreement and disagreement remain stored in `source_claims` and are not yet incorporated into credibility propagation.

Current schema:

claims

```text
claim_id
product_id
attribute
```

source_claims

```text
source_id
product_id
claim_id
canonical_attribute
value_string
value_numeric
unit
```

I've basically moved claims up to be product attributes, and sources have now begun to make potentially contradictory value assertions about these product attributes.

Previous claim support distribution:

```text
1 source -> 11,855 claims
2 sources -> 724 claims
3 sources -> 165 claims
4 sources -> 32 claims
5 sources -> 6 claims
6 sources -> 1 claim
```

Approximately 92% of claims were supported by a single source.

This now shifts to:

```text
1 source -> 8,030 claims
2 sources -> 1,822 claims
3 sources -> 575 claims
4 sources -> 163 claims
5 sources -> 32 claims
6 sources -> 8 claims
```

Single source claims went down from about 92% of all claims to about 75.5% and multi source claims increased as much as ~152% for two source claims, ~248% for three source claims, and ~409% for four source claims.

It was an unexpected, but welcomed change to dramatically reduce the graph sparsity simply by moving claims to represent a product attribute, rather than a product attribute and its corresponding value.

The new graph has 24 sources and 10,629 claims.

This yielded 14,255 source-claims, and a propagation from source to claim and back, similar to what we had previously, but on the source to attribute pair.

Here, the propagation from source to claim and back (source -> claim -> source) reaches a fixed point within 36 iterations if we initialize each claim to be 1/24.

With random initialization, it took only a few more iterations to reach convergence.

The two fixed points are not too far apart (1.918e-9 apart) so the initialization choice should not matter too much in relation to the other variables used.

The sources and their relative importance were similar, with bestbuy.com still dominating, but several sources which previously held value are no longer there (hp.com, dell.com, bjs.com, lenovo.com).

The propagation remains recursive, with source credibility influencing claim credibility and claim credibility influencing source credibility. The system continues to converge to a stable fixed point under multiple initializations within the graph and still is more about how the source has supported many similar claims and what claims are supported by multiple sources.

I haven't yet incorporated any level of agreement/disagreement within sources or claims, only simply reinforcement of which source supported which claim.

The graph, therefore, still does not distinguish between a source supporting a claim of, say, 200 nits and another source supporting the same claim with 300 nits.