# CPU Core Disagreement Example

The following demonstrates an example of conflicting source assertions for the same product attribute.

## Product

- Lenovo Slim 3 Chromebook
- Product ID: 196803504613

## Observed Source Assertions

```text
bestbuy.com      -> cpu_cores = 8
energystar.gov   -> cpu_cores = 8
target.com       -> cpu_cores = 8
walmart.com      -> cpu_cores = 2
```

As seen above, three sources assert 8 CPU cores while one source asserts 2 CPU cores.

There is a dispute present in `source_claims.csv`.

## Canonical Property

```text
(product_id, attribute)

The graph does not operate directly on source values.

Instead, sources connect to the canonical property through assertion edges:

```text
bestbuy.com      -> claim_1166
energystar.gov   -> claim_1166
target.com       -> claim_1166
walmart.com      -> claim_1166
```

The raw values asserted by each source are separated from the graph structure.

## Two Layers

### Source Assertions

Stored in `source_claims.csv`.

```text
bestbuy.com      cpu_cores = 8
energystar.gov   cpu_cores = 8
target.com       cpu_cores = 8
walmart.com      cpu_cores = 2
```

This is where we measure agreement and disagreement.

### Graph Structure

Stored in `claims.csv` and `assertions.csv`.

```text
bestbuy.com      -> claim_1166
energystar.gov   -> claim_1166
target.com       -> claim_1166
walmart.com      -> claim_1166
```

The verifier and credibility propagation operate on this layer.

## Files

- `product.csv` — product metadata
- `source_claims.csv` — source-specific assertions
- `claims.csv` — canonical properties
- `assertions.csv` — source -> claim graph edges
