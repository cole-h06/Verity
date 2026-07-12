import os
import sqlite3

from collections import defaultdict


DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "verity_v1.db"
)

# we start every source with equal weight
def initialize_vector(source_ids):

    n = len(source_ids)

    return {
        source_id: 1.0 / n
        for source_id in source_ids
    }


# source credibility flows into claims
def score_claims(
    credibility,
    claim_to_sources
):

    claim_support = {}

    for claim_id, source_ids in claim_to_sources.items():

        support = 0.0

        for source_id in source_ids:
            support += credibility[source_id]

        claim_support[claim_id] = support

    return claim_support

# claims push credibility back into sources
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
            support_sum / len(claim_ids)
        )

    return next_credibility

# otherwise scores grow every iteration
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

# simple recursive update loop
def run_iterations(
    source_to_claims,
    claim_to_sources,
    iterations=20
):

    credibility = initialize_vector(
        source_to_claims.keys()
    )

    for iteration in range(iterations):

        if iteration % 5 == 0:

            print(
                f"iteration {iteration + 1}"
            )

        claim_support = score_claims(
            credibility,
            claim_to_sources
        )

        credibility = update_sources(
            claim_support,
            source_to_claims
        )

        credibility = normalize(
            credibility
        )

    return credibility, claim_support


def main():

    print()
    print("loading assertion graph...")
    print()

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

    print(
        f"loaded {len(source_to_claims)} sources"
    )

    print(
        f"loaded {len(claim_to_sources)} claims"
    )

    print()
    print("running credibility iterations...")
    print()

    credibility, claim_support = run_iterations(
        source_to_claims,
        claim_to_sources
    )

    print()
    print("top sources")
    print()

    print()
    print("top claims")
    print()

    cursor.execute("""
        SELECT
            claim_id,
            product_id,
            attribute,
            value_string
        FROM claims
    """)

    claim_info = {}

    for row in cursor.fetchall():

        claim_info[row[0]] = (
            row[1],
            row[2],
            row[3]
        )

    for claim_id, support in sorted(
        claim_support.items(),
        key=lambda x: x[1],
        reverse=True
    )[:20]:

        product_id, attribute, value = (
            claim_info.get(
                claim_id,
                ("?", "?", "?")
            )
        )

        print(
            f"{support:.6f}  "
            f"{attribute} = {value}"
        )

    for source_id, score in sorted(
        credibility.items(),
        key=lambda x: x[1],
        reverse=True
    )[:20]:

        domain = source_names.get(
            source_id,
            str(source_id)
        )

        claim_count = len(
            source_to_claims[source_id]
        )

        print(
            f"{domain:<25}"
            f"{score:.6f}  "
            f"claims={claim_count}"
        )

    print()


if __name__ == "__main__":
    main()
