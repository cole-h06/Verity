# Experiment 9 - Agreement Structure

Date: June 23, 2026

## Background

In earlier Verity iterations, a claim was defined as:

```text
(product_id, attribute, value)
```

With this schema, sources only connected when they asserted the exact same value.

This resulted in a highly sparse graph where almost every claim was only supported by one source.

In order to increase overlap between sources, we redefined claims in Experiment 7:

```text
(product_id, attribute)
```

Values are now stored only in `source_claims`.

This created two distinct layers:

```text
source_claims
```

A table for value-level assertions and disagreements.

```text
claims + assertions
```

The graph structure used by the verifier for its graph traversal.

## Goal

Determine how much agreement and disagreement there is between the sources after migrating to attribute-level claims.

This experiment is not intended to modify the credibility scores; instead it's measuring how agreement and disagreement are distributed throughout the graph.

## Method

The assertions were grouped by:

```text
(product_id, attribute)
```

For each group:

```text
largest agreeing value group
----------------------------
total assertions
```

Agreement score examples:

```text
[8, 8, 8]
agreement = 1.00
```

```text
[8, 8, 2]
agreement = 0.67
```

```text
[8, 4, 2]
agreement = 0.33
```

Presently, agreement is still source-independent - all sources contribute equally regardless of their credibility.

Example

Product:

```text
Lenovo Slim 3 Chromebook
196803504613
```

Observed assertions:

```text
bestbuy.com      -> cpu_cores = 8
energystar.gov   -> cpu_cores = 8
target.com       -> cpu_cores = 8
walmart.com      -> cpu_cores = 2
```

Agreement:

```text
3 / 4 = 0.75
```

At the graph layer:

```text
bestbuy.com      -> claim_1166
energystar.gov   -> claim_1166
target.com       -> claim_1166
walmart.com      -> claim_1166
```

Each source is now linked to the same canonical property, despite disagreeing on the value.

## Observations

Agreement and disagreement relationships are now visible throughout the graph.

The new representation allows:

* measurement of agreement
* measurement of disagreement
* inspection of conflicting source assertions
* comparison of source overlap and value overlap

These relationships were hidden under the previous claim definition because each value created a separate claim node.

## Current Limitation

Agreement is not yet part of credibility propagation.

The verifier only sees:

```text
source -> claim -> source
```

through assertion edges.

Disagreement is measured but not yet incorporated into the propagation process.

## Next Question

Possible directions include:

* rewarding agreement
* penalizing disagreement
* weighting claims by agreement strength
* separating competing value clusters
* modeling source dependence and copying

How agreement and disagreement should influence credibility remains an open question.
