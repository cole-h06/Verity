# run_benchmark.py

import os

from credibility.loader import (
    load_from_csv
)

from credibility.v7 import (
    run
)


def main():

    benchmark = os.path.join(
        os.path.dirname(__file__),
        "benchmark"
    )

    print()
    print("loading benchmark...")
    print()

    (
        source_to_claims,
        claim_to_sources,
        source_names,
        agreement_weights
    ) = load_from_csv(
        benchmark
    )

    print("running credibility inference...")
    print()

    run(
        source_to_claims,
        claim_to_sources,
        source_names,
        agreement_weights
    )


if __name__ == "__main__":
    main()