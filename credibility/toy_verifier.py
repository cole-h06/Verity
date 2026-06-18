import random

from collections import defaultdict


# A and B share claims.

# D only supports claims
# that point back to D.

# A -- C1 -- B
# A -- C2 -- B
#
# D -- C3
# D -- C4

source_to_claims = {
    "A": {"C1", "C2"},
    "B": {"C1", "C2"},
    "D": {"C3", "C4"}
}

claim_to_sources = {
    "C1": {"A", "B"},
    "C2": {"A", "B"},
    "C3": {"D"},
    "C4": {"D"}
}


# we repeatedly move from
# source -> claim -> source
# and count how often
# each source is revisited
def run_verifier(
    start_source,
    steps
):

    current_source = start_source

    visits = defaultdict(int)

    visits[current_source] += 1

    for _ in range(steps):

        # choose one claim
        # from the source

        claim = random.choice(
            list(
                source_to_claims[
                    current_source
                ]
            )
        )

        # choose one source
        # from the claim

        current_source = random.choice(
            list(
                claim_to_sources[
                    claim
                ]
            )
        )

        visits[current_source] += 1

    return visits


# display visit frequency
def print_results(
    title,
    visits
):

    total = sum(
        visits.values()
    )

    print()
    print(title)
    print("-" * len(title))

    for source in sorted(visits):

        percent = (
            visits[source]
            / total
        ) * 100

        print(
            f"{source:<10}"
            f"{percent:.2f}%"
        )


def main():

    steps = 100_000

    visits = run_verifier(
        start_source="A",
        steps=steps
    )

    print_results(
        "starting from A",
        visits
    )

    visits = run_verifier(
        start_source="D",
        steps=steps
    )

    print_results(
        "starting from D",
        visits
    )

    print()


if __name__ == "__main__":
    main()
