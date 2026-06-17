# CPU Core Disagreement Example

The following is an example of conflicting source assertions for the same product attribute.

Product:

* Lenovo Slim 3 Chromebook
* Product ID: 196803504613

Canonical claim:

```text
claim = (product_id, attribute)
```

Sources assert values through `source_claims` and connect to canonical claims through `assertions`.

Observed assertions:

```text
bestbuy.com      -> cpu_cores = 8
energystar.gov   -> cpu_cores = 8
target.com       -> cpu_cores = 8
walmart.com      -> cpu_cores = 2
```

Files:

* `product.csv` - product metadata
* `claims.csv` - canonical claims
* `source_claims.csv` - source-specific assertions
* `assertions.csv` - bipartite graph edges
