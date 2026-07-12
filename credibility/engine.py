# v7.py

import os
import random


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
    source_to_claims,
    agreement_weights
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

            edge_weight = agreement_weights.get(
                (
                    source_id,
                    claim_id
                ),
                1.0
            )

            support += (
                credibility[source_id]
                * edge_weight
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

        next_credibility[source_id] = support_sum

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
    agreement_weights,
    tolerance=1e-8,
    max_iterations=1000,
    return_history=False
):

    iteration = 0

    history = []

    while iteration < max_iterations:

        previous = credibility.copy()

        # source -> claim
        claim_support = score_claims(
            credibility,
            claim_to_sources,
            source_to_claims,
            agreement_weights
        )

        # claim -> source
        credibility = update_sources(
            claim_support,
            source_to_claims
        )

        credibility = normalize(
            credibility
        )

        # we measure how much the
        # credibility vector changed
        maximum_difference = 0.0

        for source_id in credibility:

            difference = abs(
                credibility[source_id]
                - previous[source_id]
            )

            if difference > maximum_difference:
                maximum_difference = difference

        history.append(
            maximum_difference
        )

        print(
            f"iteration "
            f"{iteration + 1:>3}   "
            f"delta = "
            f"{maximum_difference:.12f}"
        )

        # once the vector stops moving
        # we consider it converged
        if maximum_difference < tolerance:

            print()
            print(
                f"converged after "
                f"{iteration + 1} "
                f"iterations"
            )

            if return_history:
                return (
                    credibility,
                    history
                )

            return credibility

        iteration += 1

    print()
    print(
        "maximum iterations reached"
    )

    if return_history:
        return (
            credibility,
            history
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


def compare_rankings(
    baseline,
    weighted,
    source_names,
    n=20
):

    rows = []

    for source_id in weighted:

        before = baseline.get(
            source_id,
            0.0
        )

        after = weighted[
            source_id
        ]

        change = (
            after
            - before
        )

        rows.append(
            (
                abs(change),
                change,
                source_id,
                before,
                after
            )
        )

    rows.sort(
        reverse=True
    )

    print()
    print("largest agreement effects")
    print("-------------------------")

    for (
        _,
        change,
        source_id,
        before,
        after
    ) in rows[:n]:

        domain = source_names.get(
            source_id,
            str(source_id)
        )

        print(
            f"{domain:<30}"
            f"{before:.8f}  "
            f"{after:.8f}  "
            f"{change:+.8f}"
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


# store final credibility scores
# so we can compare experiments
# across graph revisions
def save_scores(
    credibility,
    source_names,
    filename
):

    path = os.path.join(
        os.path.dirname(__file__),
        filename
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "source_id,domain,score\n"
        )

        for source_id, score in sorted(
            credibility.items(),
            key=lambda x: x[1],
            reverse=True
        ):

            domain = source_names.get(
                source_id,
                str(source_id)
            )

            f.write(
                f"{source_id},"
                f"{domain},"
                f"{score:.12f}\n"
            )

    print()
    print(
        f"saved scores to {path}"
    )


def run(
    source_to_claims,
    claim_to_sources,
    source_names,
    agreement_weights,
    save=True
):

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

    # compare agreement-weighted
    # propagation against a baseline
    # where every assertion edge
    # receives equal weight
    baseline_weights = {

        (
            source_id,
            claim_id
        ): 1.0

        for source_id, claim_ids
        in source_to_claims.items()

        for claim_id
        in claim_ids
    }

    print()
    print("running uniform initialization...")

    uniform = initialize_uniform(
        source_ids
    )

    uniform = run_until_convergence(
        source_to_claims,
        claim_to_sources,
        uniform,
        agreement_weights
    )

    if save:

        save_scores(
            uniform,
            source_names,
            "v7_scores.csv"
        )

    print()
    print("running unweighted baseline...")

    baseline = initialize_uniform(
        source_ids
    )

    baseline = run_until_convergence(
        source_to_claims,
        claim_to_sources,
        baseline,
        baseline_weights
    )

    # measure how much the final
    # credibility rankings changed
    # after introducing agreement
    compare_rankings(
        baseline,
        uniform,
        source_names
    )

    print()
    print("running random initialization...")

    random_scores = initialize_random(
        source_ids
    )

    random_scores = run_until_convergence(
        source_to_claims,
        claim_to_sources,
        random_scores,
        agreement_weights
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

    print("maximum difference between ""initializations:")

    print(
        f"{difference:.12f}"
    )

    print()

    if difference < 1e-8:

        print("same fixed point reached")

    else:

        print("different solutions found")

    print()

    return {
        "credibility": uniform,
        "baseline": baseline,
        "difference": difference,
    }