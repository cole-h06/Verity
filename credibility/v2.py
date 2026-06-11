import os
import sqlite3
import random

from collections import defaultdict


DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "verity_v1.db"
)


def initialize_uniform(source_ids):
    """
    Give every source equal credibility.
    """

    n = len(source_ids)

    return {
        source_id: 1.0 / n
        for source_id in source_ids
    }


def initialize_random(source_ids):
    """
    Start with random credibility scores.
    """

    scores = {
        source_id: random.random()
        for source_id in source_ids
    }

    return normalize_distribution(
        scores
    )


def compute_claim_support(
    credibility,
    claim_to_sources,
    source_to_claims
):
    """
    Distribute source credibility
    across all claims asserted by
    that source.
    """

    claim_support = {}

    for claim_id, source_ids in claim_to_sources.items():

        support = 0.0

        for source_id in source_ids:

            degree = len(
                source_to_claims[source_id]
            )

            if degree == 0:
                continue

            support += (
                credibility[source_id]
                / degree
            )

        claim_support[claim_id] = support

    return claim_support


def propagate_credibility(
    claim_support,
    source_to_claims
):
    """
    Sources inherit credibility from
    the claims they assert.
    """

    next_credibility = {}

    for source_id, claim_ids in source_to_claims.items():

        if not claim_ids:
            next_credibility[source_id] = 0.0
            continue

        support_sum = 0.0

        for claim_id in claim_ids:
            support_sum += claim_support[claim_id]

        next_credibility[source_id] = (
            support_sum / len(claim_ids)
        )

    return next_credibility


def normalize_distribution(
    credibility
):
    """
    Keep total credibility fixed.
    """

    total = sum(
        credibility.values()
    )

    if total == 0:
        return credibility

    return {
        source_id: score / total
        for source_id, score
        in credibility.items()
    }


def run_power_iteration(
    source_to_claims,
    claim_to_sources,
    credibility,
    iterations=20
):
    """
    Repeatedly propagate credibility
    through the graph.
    """

    for _ in range(iterations):

        claim_support = compute_claim_support(
            credibility,
            claim_to_sources,
            source_to_claims
        )

        credibility = propagate_credibility(
            claim_support,
            source_to_claims
        )

        credibility = normalize_distribution(
            credibility
        )

    return credibility


def compare_distributions(
    first,
    second
):
    """
    Measure the largest difference
    between two final distributions.
    """

    maximum_difference = 0.0

    for source_id in first:

        difference = abs(
            first[source_id]
            - second[source_id]
        )

        if difference > maximum_difference:
            maximum_difference = difference

    return maximum_difference


def load_graph():

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    source_to_claims = defaultdict(set)
    claim_to_sources = defaultdict(set)

    source_names = {}

    cursor.execute("""
        SELECT
            id,
            domain
        FROM sources
    """)

    for source_id, domain in cursor.fetchall():

        source_names[source_id] = domain

    cursor.execute("""
        SELECT
            source_id,
            claim_id
        FROM assertions
    """)

    for source_id, claim_id in cursor.fetchall():

        source_to_claims[source_id].add(
            claim_id
        )

        claim_to_sources[claim_id].add(
            source_id
        )

    conn.close()

    return (
        source_to_claims,
        claim_to_sources,
        source_names
    )


def print_top_sources(
    title,
    credibility,
    source_names
):

    print()
    print(title)
    print("-" * len(title))

    for source_id, score in sorted(
        credibility.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10]:

        domain = source_names.get(
            source_id,
            str(source_id)
        )

        print(
            f"{domain:<25}"
            f"{score:.6f}"
        )


def main():

    print()
    print("loading assertion graph...")
    print()

    (
        source_to_claims,
        claim_to_sources,
        source_names
    ) = load_graph()

    print(
        f"sources: {len(source_to_claims)}"
    )

    print(
        f"claims: {len(claim_to_sources)}"
    )

    source_ids = list(
        source_to_claims.keys()
    )

    print()
    print("running uniform initialization...")
    print()

    uniform = initialize_uniform(
        source_ids
    )

    uniform = run_power_iteration(
        source_to_claims,
        claim_to_sources,
        uniform
    )

    print()
    print("running random initialization...")
    print()

    random_scores = initialize_random(
        source_ids
    )

    random_scores = run_power_iteration(
        source_to_claims,
        claim_to_sources,
        random_scores
    )

    difference = compare_distributions(
        uniform,
        random_scores
    )

    print_top_sources(
        "uniform initialization",
        uniform,
        source_names
    )

    print_top_sources(
        "random initialization",
        random_scores,
        source_names
    )

    print()
    print(
        f"maximum difference: "
        f"{difference:.10f}"
    )
    print()


if __name__ == "__main__":
    main()