# Claim Redefinition

June 17, 2026

I found that nearly all (92%) of the claims were supported by a single source, indicating that claims may have been too specific, creating an overly sparse graph.

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

The propagation algorithm still works on the source-claim bipartite graph, however, claims at this point refer to to shared product attributes instead of asserted values specifically.

Both agreement and disagreement are stored independently in `source_claims`. This allows for multiple sources to connect through the same claim but assert differing values.

This decoupling of graph structure from value agreement set the foundation for agreement-weighted propagation and eventually for source dependencies.
