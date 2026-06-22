# verifier.py

import os
import sqlite3
import random

from collections import defaultdict


DB = os.path.join(
    os.path.dirname(__file__),
    "..",
    "verity_v1.db"
)


# load the bipartite graph
# from sqlite
def load_assertion_graph():

    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    source_to_claims = defaultdict(set)
    claim_to_sources = defaultdict(set)

    source_names = {}
    domain_to_id = {}

    cursor.execute("""
        SELECT
            id,
            domain
        FROM sources
    """)

    for source_id, domain in cursor.fetchall():

        source_names[source_id] = domain
        domain_to_id[domain] = source_id

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
        source_names,
        domain_to_id
    )


# we repeatedly move from
# source -> claim -> source
# and count how often
# each source is revisited
def run_verifier(
    source_to_claims,
    claim_to_sources,
    start_source,
    steps
):

    current_source = start_source

    visits = defaultdict(int)

    visits[current_source] += 1

    for _ in range(steps):

        claim_ids = list(
            source_to_claims[
                current_source
            ]
        )

        if not claim_ids:
            break

        # choose one claim
        # from the source

        claim_id = random.choice(
            claim_ids
        )

        source_ids = list(
            claim_to_sources[
                claim_id
            ]
        )

        if not source_ids:
            break

        # choose one source
        # from the claim

        current_source = random.choice(
            source_ids
        )

        visits[current_source] += 1

    return visits


# display the most visited
# sources
def print_top_sources(
    visits,
    source_names,
    n=20
):

    total = sum(
        visits.values()
    )

    print()
    print("top visited sources")
    print("-------------------")

    for source_id, count in sorted(
        visits.items(),
        key=lambda x: x[1],
        reverse=True
    )[:n]:

        percent = (
            count / total
        ) * 100

        print(f"{source_names[source_id]:<30}" f"{percent:.2f}%")


def main():

    print()
    print("loading assertion graph...")

    (
        source_to_claims,
        claim_to_sources,
        source_names,
        domain_to_id
    ) = load_assertion_graph()

    print(f"sources: {len(source_to_claims)}")

    print(f"claims: {len(claim_to_sources)}")

    print()

    start_domain = "lenovo.com"

    start_source = domain_to_id[
        start_domain
    ]

    steps = 1_000_000

    print(f"starting source: {start_domain}")

    print(f"steps: {steps}")

    visits = run_verifier(
        source_to_claims,
        claim_to_sources,
        start_source,
        steps
    )

    print()

    print(f"unique sources visited: " f"{len(visits)}")

    print(f"total visits: " f"{sum(visits.values())}")

    print_top_sources(visits, source_names)

    print()
    print("unvisited sources")
    print("-----------------")

    for source_id, domain in sorted(
        source_names.items(),
        key=lambda x: x[1]
    ):

        if source_id not in visits:
            print(domain)

    print()


if __name__ == "__main__":
    main()