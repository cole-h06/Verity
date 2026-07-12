# v6_agreement_edges.py

import os
import sqlite3

from collections import Counter
from collections import defaultdict

from canonical_graph import (
    GRAPH_ATTRIBUTES,
    canonicalize
)


DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "verity_v1.db"
)


# Load the same subset of source claims
# used by the graph experiments
#
# We keep the dataset identical for direct
# comparison with previous runs
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

# Remove source assertions where a
# single source emitted multiple values
# for the same product property
#
# These cases are ambiguous and are
# excluded from agreement calculations
def remove_ambiguous(rows):

    print()
    print("removing ambiguous assertions...")

    groups = defaultdict(set)

    clean_rows = []

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
            continue

        key = (
            source_id,
            product_id,
            attribute
        )

        groups[key].add(
            value
        )

    allowed = {

        key

        for key, values
        in groups.items()

        if len(values) == 1
    }

    for row in rows:

        key = (
            row[0],
            row[1],
            row[2]
        )

        if key in allowed:

            clean_rows.append(
                row
            )

        else:

            skipped += 1

    print(
        f"removed: {skipped}"
    )

    print(
        f"remaining: {len(clean_rows)}"
    )

    return clean_rows


# Group assertions by:
#
# (product_id, attribute)
#
# Example:
#
# MacBook
# cpu_cores
#
# 8
# 8
# 8
# 2
#
# All four assertions belong
# to the same property group
def build_groups(rows):

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

        key = (
            product_id,
            attribute
        )

        groups[key].append(
            (
                source_id,
                value
            )
        )

    print(f"skipped: {skipped}")

    return groups


# Agreement weight:
#
# value_support
# -------------
# total_support
#
# Example:
#
# [8, 8, 8, 2]
#
# value 8:
#
# 3 / 4 = 0.75
#
# value 2:
#
# 1 / 4 = 0.25
#
# These weights are the first step
# toward agreement-aware propagation
def build_edges(groups):

    edges = []

    for key, assertions in groups.items():

        values = [

            value

            for _, value
            in assertions
        ]

        total_support = len(
            values
        )

        counts = Counter(
            values
        )

        for source_id, value in assertions:

            value_support = counts[
                value
            ]

            weight = (
                value_support
                / total_support
            )

            edges.append(
                {
                    "product_id": key[0],
                    "attribute": key[1],
                    "source_id": source_id,
                    "value": value,
                    "support": value_support,
                    "total": total_support,
                    "weight": weight
                }
            )

    return edges


# Show the strongest disagreements
#
# Useful for checking whether the
# weights make intuitive sense
def show_examples(edges):

    print()
    print("agreement edge examples")
    print("-----------------------")

    shown = 0

    edges = sorted(
        edges,
        key=lambda x: (
            x["weight"],
            -x["total"]
        )
    )

    for edge in edges:

        if shown >= 20:
            break

        if edge["weight"] == 1.0:
            continue

        print()

        print(
            f"product: "
            f"{edge['product_id']}"
        )

        print(
            f"attribute: "
            f"{edge['attribute']}"
        )

        print(
            f"value: {edge['value']}"
        )

        print(
            f"support: "
            f"{edge['support']}"
            f"/"
            f"{edge['total']}"
        )

        print(
            f"weight: "
            f"{edge['weight']:.3f}"
        )

        shown += 1


# Show complete disagreement groups
#
# This makes it easier to determine whether
# disagreements are real or caused by
# normalization/extraction issues
def show_groups(groups):

    print()
    print("largest disagreements")
    print("---------------------")

    rows = []

    for (
        product_id,
        attribute
    ), assertions in groups.items():

        values = [

            value

            for _, value
            in assertions
        ]

        support = len(
            values
        )

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
            continue

        rows.append(
            (
                agreement,
                support,
                product_id,
                attribute,
                counts
            )
        )

    rows.sort(
        key=lambda x: (
            x[0],
            -x[1]
        )
    )

    for (
        agreement,
        support,
        product_id,
        attribute,
        counts
    ) in rows[:20]:

        print()

        print(
            f"product: {product_id}"
        )

        print(
            f"attribute: {attribute}"
        )

        print(
            f"agreement: "
            f"{agreement:.3f}"
        )

        print(
            f"support: {support}"
        )

        print("values:")

        for value, count in sorted(
            counts.items(),
            key=lambda x: x[1],
            reverse=True
        ):

            print(
                f"  {value:<20}"
                f"{count}"
            )


# Broad overview of how much
# discounting is occurring
def summary(edges):

    buckets = defaultdict(int)

    for edge in edges:

        bucket = round(
            edge["weight"],
            1
        )

        buckets[
            bucket
        ] += 1

    print()
    print("edge weight distribution")
    print("------------------------")

    for bucket in sorted(
        buckets
    ):

        print(
            f"{bucket:.1f}"
            f" -> "
            f"{buckets[bucket]}"
        )


def main():

    rows = load_claims()

    rows = remove_ambiguous(
        rows
    )

    print()
    print("building groups...")

    groups = build_groups(
        rows
    )

    print()
    print("building agreement edges...")

    edges = build_edges(
        groups
    )

    summary(
        edges
    )

    show_groups(
        groups
    )

    show_examples(
        edges
    )

    print()


if __name__ == "__main__":
    main()
