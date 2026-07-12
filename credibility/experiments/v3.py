# v3.py

import os
import sqlite3
import random

from collections import defaultdict


DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "verity_v1.db"
)


# start every source with equal credibility
def initialize_uniform(source_ids):

    n = len(source_ids)

    return {
        source_id: 1.0 / n
        for source_id in source_ids
    }


# random initialization lets us test
# whether the system converges
# to the same solution
def initialize_random(source_ids):

    scores = {
        source_id: random.random()
        for source_id in source_ids
    }

    return normalize(
        scores
    )


# distribute source credibility
# across the claims it asserts
def score_claims(
    credibility,
    claim_to_sources,
    source_to_claims
):

    claim_support = {}

    for claim_id, source_ids in claim_to_sources.items():

        support = 0.0

        for source_id in source_ids:

            # sources with many claims
            # split their credibility
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


# claims propagate support
# back into their sources
def update_sources(
    claim_support,
    source_to_claims
):

    next_credibility = {}

    for source_id, claim_ids in source_to_claims.items():

        if not claim_ids:
            next_credibility[source_id] = 0.0
            continue

        support_sum = 0.0

        for claim_id in claim_ids:
            support_sum += claim_support[claim_id]

        next_credibility[source_id] = (
            support_sum
            / len(claim_ids)
        )

    return next_credibility


# keep the credibility vector
# on a fixed scale
def normalize(
    credibility
):

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


# repeatedly pass credibility
# through the graph until
# the scores stop changing
def run_until_convergence(
    source_to_claims,
    claim_to_sources,
    credibility,
    tolerance=1e-8,
    max_iterations=1000
):

    iteration = 0

    while iteration < max_iterations:

        previous = credibility.copy()

        # source -> claim
        claim_support = score_claims(
            credibility,
            claim_to_sources,
            source_to_claims
        )

        # claim -> source
        credibility = update_sources(
            claim_support,
            source_to_claims
        )

        credibility = normalize(
            credibility
        )

        # measure how much
        # the vector changed
        maximum_difference = 0.0

        for source_id in credibility:

            difference = abs(
                credibility[source_id]
                - previous[source_id]
            )

            if difference > maximum_difference:
                maximum_difference = difference

        print(
            f"iteration "
            f"{iteration + 1:>3}   "
            f"delta = "
            f"{maximum_difference:.12f}"
        )

        # stop once the
        # vector stabilizes
        if maximum_difference < tolerance:

            print()
            print(
                f"converged after "
                f"{iteration + 1} "
                f"iterations"
            )

            return credibility

        iteration += 1

    print()
    print(
        "maximum iterations reached"
    )

    return credibility


# compare two credibility vectors
def compare_results(
    first,
    second
):

    maximum_difference = 0.0

    for source_id in first:

        difference = abs(
            first[source_id]
            - second[source_id]
        )

        if difference > maximum_difference:
            maximum_difference = difference

    return maximum_difference


# load the graph
# from sqlite
def load_assertion_graph():

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
    source_names,
    n=20
):

    print()
    print(title)
    print("-" * len(title))

    for source_id, score in sorted(
        credibility.items(),
        key=lambda x: x[1],
        reverse=True
    )[:n]:

        domain = source_names.get(
            source_id,
            str(source_id)
        )

        print(
            f"{domain:<30}"
            f"{score:.8f}"
        )


def print_bottom_sources(
    title,
    credibility,
    source_names,
    n=20
):

    print()
    print(title)
    print("-" * len(title))

    for source_id, score in sorted(
        credibility.items(),
        key=lambda x: x[1]
    )[:n]:

        domain = source_names.get(
            source_id,
            str(source_id)
        )

        print(
            f"{domain:<30}"
            f"{score:.8f}"
        )


def main():

    print()
    print(
        "loading assertion graph..."
    )
    print()

    (
        source_to_claims,
        claim_to_sources,
        source_names
    ) = load_assertion_graph()

    print(
        f"sources: "
        f"{len(source_to_claims)}"
    )

    print(
        f"claims: "
        f"{len(claim_to_sources)}"
    )

    print(
        f"assertions: "
        f"{sum(
            len(v)
            for v
            in source_to_claims.values()
        )}"
    )

    source_ids = list(
        source_to_claims.keys()
    )

    print()
    print(
        "running uniform initialization..."
    )

    uniform = initialize_uniform(
        source_ids
    )

    uniform = run_until_convergence(
        source_to_claims,
        claim_to_sources,
        uniform
    )

    print()
    print(
        "running random initialization..."
    )

    random_scores = initialize_random(
        source_ids
    )

    random_scores = run_until_convergence(
        source_to_claims,
        claim_to_sources,
        random_scores
    )

    difference = compare_results(
        uniform,
        random_scores
    )

    print_top_sources(
        "top sources (uniform)",
        uniform,
        source_names
    )

    print_bottom_sources(
        "bottom sources (uniform)",
        uniform,
        source_names
    )

    print()

    print(
        "maximum difference between "
        "initializations:"
    )

    print(
        f"{difference:.12f}"
    )

    print()

    if difference < 1e-8:

        print(
            "same fixed point reached"
        )

    else:

        print(
            "different solutions found"
        )

    print()


if __name__ == "__main__":
    main()
