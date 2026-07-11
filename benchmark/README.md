# Verity Benchmark

This is the directory containing the benchmark dataset used for developing the Verity credibility inference engine.

With this benchmark, you can experiment with:

- Credibility propagation
- Agreement weighting
- Source dependency modeling

## Running the benchmark

Clone the repository.

```bash
git clone https://github.com/cole-h06/Verity.git
cd Verity
```

From the project root, run:

```bash
python3 run_benchmark.py
```

## Tables

- `sources.csv` - source identifiers
- `claims.csv` - claim nodes
- `source_claims.csv` - source-specific values
- `assertions.csv` - edges connecting sources to claims

Product specifications are currently the benchmark being used for development as they provide large amounts of conflicting data published by independent sources. That said, the inference algorithms themselves are not limited by any specific domain and operate only on graph structure.
