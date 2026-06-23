# v5_agreement.py

import os
import sqlite3

from collections import Counter
from collections import defaultdict

from simulate_graph import (
    GRAPH_ATTRIBUTES,
    canonicalize
)


DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "verity_v1.db"
)


# Pull the subset of source claims that
# participate in the Verity graph
#
# We intentionally reuse the same attributes
# and canonicalization pipeline as
# canonical_graph.py
# This way, we have both experiments operating 
# on identical data
def load_claims():

    print()
    print("loading source claims...")

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            source_id,
            product_id,
            canonical_attribute,
            value_string,
            value_numeric,
            unit
        FROM source_claims
    """)

    rows = [

        row

        for row in cursor.fetchall()

        if row[2] in GRAPH_ATTRIBUTES
    ]

    conn.close()

    print(f"rows: {len(rows)}")

    return rows


# We group assertions by: (product_id, attribute)
#
# This is the architecture currently
# being explored for Verity
#
# Sources discussing the same product
# attribute land in the same bucket even if
# they disagree on the final value
#
# Example:
#
# MacBook Pro
# bluetooth_version
#
# Amazon     -> 5.3
# Best Buy   -> 5.3
# Target     -> 5.2
#
# All three assertions belong to the same
# property group
def build_property_groups(rows):

    groups = defaultdict(list)

    skipped = 0

    for (
        source_id,
        product_id,
        attribute,
        value_string,
        value_numeric,
        unit
    ) in rows:

        if value_numeric is not None:

            value = str(
                value_numeric
            )

        else:

            value = value_string

        value = canonicalize(
            attribute,
            value
        )

        if value is None:

            skipped += 1
            continue

        property_key = (
            product_id,
            attribute
        )

        groups[
            property_key
        ].append(
            (
                source_id,
                value
            )
        )

    print(f"skipped: {skipped}")

    return groups


# Measure agreement within each
# (product, attribute) bucket
#
# Agreement is currently defined as:
#
# largest agreeing group
# ----------------------
# total assertions
#
# Examples:
#
# [5.3, 5.3, 5.3]
# agreement = 1.00
#
# [5.3, 5.3, 5.2]
# agreement = 0.67
#
# [5.3, 5.2, 5.1]
# agreement = 0.33
#
# At this stage we are only measuring the
# structure of agreement. Source credibility
# is not yet involved
def calculate_agreement(groups):

    results = []

    perfect = 0
    partial = 0

    for property_key, assertions in groups.items():

        values = [

            value

            for _, value
            in assertions
        ]

        support = len(values)

        if support < 2:
            continue

        counts = Counter(
            values
        )

        largest_group = max(
            counts.values()
        )

        agreement = (
            largest_group
            / support
        )

        if agreement == 1.0:
            perfect += 1
        else:
            partial += 1

        results.append(
            {
                "property": property_key,
                "support": support,
                "agreement": agreement,
                "counts": counts
            }
        )

    return (
        results,
        perfect,
        partial
    )


# A conceptual summary of how much
# agreement exists in the graph
def print_summary(
    results,
    perfect,
    partial
):

    print()
    print("agreement summary")
    print("-----------------")

    print(f"perfect agreement: {perfect}")

    print(f"partial agreement: {partial}")

    print(f"total multi-source properties: {len(results)}")


# Bucket agreement scores into broad ranges
# so we can see whether the graph tends
# toward consensus or disagreement overall.
def agreement_distribution(results):

    buckets = defaultdict(int)

    for result in results:

        agreement = result[
            "agreement"
        ]

        bucket = round(
            agreement,
            1
        )

        buckets[
            bucket
        ] += 1

    print()
    print("agreement distribution")
    print("----------------------")

    for bucket in sorted(
        buckets
    ):

        print(
            f"{bucket:.1f}"
            f" -> "
            f"{buckets[bucket]}"
        )


# Show the most interesting disagreement
# examples so we can inspect whether the
# disagreement is:
#
# - real disagreement
# - normalization issues
# - extraction mistakes
# - unit conversion problems
#
# This is mainly a debugging tool.
def print_examples(results):

    print()
    print("agreement examples")
    print("------------------")

    shown = 0

    results = sorted(
        results,
        key=lambda x: (
            x["agreement"],
            -x["support"]
        )
    )

    for result in results:

        if shown >= 20:
            break

        agreement = result[
            "agreement"
        ]

        if agreement == 1.0:
            continue

        product_id, attribute = (
            result["property"]
        )

        print()
        print(f"product: {product_id}")

        print(f"attribute: {attribute}")

        print(f"support: {result['support']}")

        print(f"agreement: {agreement:.3f}")

        print("values:")

        for value, count in sorted(
            result["counts"].items(),
            key=lambda x: x[1],
            reverse=True
        ):

            print(
                f"  {value:<30}"
                f"{count}"
            )

        shown += 1


def main():

    rows = load_claims()

    print()
    print("building property groups...")

    groups = build_property_groups(
        rows
    )

    (
        results,
        perfect,
        partial
    ) = calculate_agreement(
        groups
    )

    print_summary(
        results,
        perfect,
        partial
    )

    agreement_distribution(
        results
    )

    print_examples(
        results
    )

    print()


if __name__ == "__main__":
    main()
