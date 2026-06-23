# canonical_graph.py

import os
from normalization import canonicalize
import sqlite3
import hashlib

from collections import defaultdict


DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "verity_v1.db"
)


GRAPH_ATTRIBUTES = {

    "ram_gb",
    "storage_gb",

    "cpu_model",
    "cpu_cores",

    "gpu_model",

    "wifi_standard",
    "bluetooth_version",

    "display_resolution",
    "screen_size",

    "battery_life_hr",

    "weight_lb",

    "operating_system",

    "touchscreen"
}


# We assign every unique claim a stable hash
#
# Sources that assert the same
# (product, attribute, value)
# end up pointing to the same claim
def build_hash(
    product_id,
    attribute,
    value,
    unit
):

    key = (
        f"{product_id}|"
        f"{attribute}|"
        f"{value}|"
        f"{unit}"
    )

    return hashlib.sha256(
        key.encode()
    ).hexdigest()


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

    print(
        f"rows: {len(rows)}"
    )

    print()
    print("graph attributes")
    print("----------------")

    for attribute in sorted(
        GRAPH_ATTRIBUTES
    ):

        print(attribute)

    return rows

# Turn normalized source assertions
# into claim nodes and source -> claim
# connections
def build_graph(rows):

    claim_to_sources = defaultdict(set)

    skipped = defaultdict(int)

    skipped_examples = defaultdict(list)

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

        original_value = value

        value = canonicalize(
            attribute,
            value
        )

        if value is None:

            skipped[
                attribute
            ] += 1

            skipped_examples[
                attribute
            ].append(
                original_value
            )

            continue

        claim_hash = build_hash(
            product_id,
            attribute,
            value,
            unit
        )

        claim_to_sources[
            claim_hash
        ].add(
            source_id
        )

    return (
        claim_to_sources,
        skipped,
        skipped_examples
    )

# Count how many sources support
# each claim
def support_breakdown(
    claim_to_sources
):

    distribution = defaultdict(int)

    for source_ids in claim_to_sources.values():

        support = len(
            source_ids
        )

        distribution[
            support
        ] += 1

    return distribution

# Measure how much of each source's
# information overlaps with other
# sources in the graph
def source_overlap(
    claim_to_sources
):

    source_total = defaultdict(int)

    source_unique = defaultdict(int)

    for source_ids in claim_to_sources.values():

        support = len(
            source_ids
        )

        for source_id in source_ids:

            source_total[
                source_id
            ] += 1

            if support == 1:

                source_unique[
                    source_id
                ] += 1

    rows = []

    for source_id in source_total:

        total = source_total[
            source_id
        ]

        unique = source_unique[
            source_id
        ]

        ratio = unique / total

        rows.append(
            (
                ratio,
                source_id,
                unique,
                total
            )
        )

    rows.sort(
        reverse=True
    )

    print()
    print("source overlap")
    print("----------------")

    for (
        ratio,
        source_id,
        unique,
        total
    ) in rows:

        conn = sqlite3.connect(DB)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT domain
            FROM sources
            WHERE id = ?
        """, (source_id,))

        result = cursor.fetchone()

        domain = (
            result[0]
            if result
            else str(source_id)
        )

        print(
            f"{domain:<25}"
            f"{unique:<5}"
            f"{total:<5}"
            f"{ratio:.3f}"
        )


def print_support(
    distribution
):

    print()
    print("support distribution")
    print("--------------------")

    for support in sorted(
        distribution
    ):

        print(
            f"{support:<4}"
            f"{distribution[support]}"
        )


def print_skipped_claims(
    skipped
):

    print()
    print("skipped claims")
    print("--------------")

    if not skipped:

        print(
            "none"
        )

        return

    for attribute, count in sorted(
        skipped.items(),
        key=lambda x: x[1],
        reverse=True
    ):

        print(
            f"{attribute:<25}"
            f"{count}"
        )

# Show examples that could not be
# normalized into graph claims
def print_skipped_examples(
    skipped_examples
):

    print()
    print("skipped examples")
    print("----------------")

    for attribute in sorted(
        skipped_examples
    ):

        print()
        print(attribute)
        print(
            "-" * len(attribute)
        )

        unique_values = sorted(
            set(
                skipped_examples[
                    attribute
                ]
            )
        )

        for value in unique_values[:50]:

            print(value)


def main():

    rows = load_claims()

    print()
    print("building graph...")

    (
        graph,
        skipped,
        skipped_examples
    ) = build_graph(
        rows
    )

    print(f"claims: {len(graph)}")

    distribution = (
        support_breakdown(
            graph
        )
    )

    print_support(
        distribution
    )

    source_overlap(
        graph
    )

    print_skipped_claims(
        skipped
    )

    print_skipped_examples(
        skipped_examples
    )

    print()


if __name__ == "__main__":
    main()