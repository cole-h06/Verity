import psycopg

from collections import defaultdict

from .canonical_graph import (
    GRAPH_ATTRIBUTES,
    canonicalize
)


def get_db():

    return psycopg.connect(
        dbname="verity_dev",
        user="colehoke",
        host="localhost"
    )


def load_sources():

    conn = get_db()
    cursor = conn.cursor()

    source_names = {}

    cursor.execute("""
        SELECT
            id,
            domain
        FROM sources
    """)

    for source_id, domain in cursor.fetchall():

        source_names[
            source_id
        ] = domain

    conn.close()

    return source_names


# build assertion sets using
# (product, attribute, value)
def load_assertions():

    conn = get_db()
    cursor = conn.cursor()

    source_to_assertions = defaultdict(dict)

    cursor.execute("""
        SELECT
            source_id,
            product_id,
            canonical_attribute,
            value_string,
            value_numeric
        FROM source_claims
        WHERE claim_id IS NOT NULL
    """)

    skipped = 0

    for (
        source_id,
        product_id,
        attribute,
        value_string,
        value_numeric
    ) in cursor.fetchall():

        if attribute not in GRAPH_ATTRIBUTES:
            continue

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

        source_to_assertions[
            source_id
        ][
            key
        ] = value

    conn.close()

    print(
        f"loaded "
        f"{sum(len(v) for v in source_to_assertions.values())} "
        f"canonical assertions"
    )

    print(
        f"skipped "
        f"{skipped} "
        f"unnormalized assertions"
    )

    return source_to_assertions


def directional_inclusion(
    a_assertions,
    b_assertions
):

    matches = 0
    disagreements = 0

    shared_keys = (
        a_assertions.keys()
        &
        b_assertions.keys()
    )

    for key in shared_keys:

        if (
            a_assertions[key]
            ==
            b_assertions[key]
        ):

            matches += 1

        else:

            disagreements += 1

    a_size = len(
        a_assertions
    )

    b_size = len(
        b_assertions
    )

    if a_size == 0 or b_size == 0:

        return (
            0,
            0,
            0.0,
            0.0,
            0.0
        )

    shared = (
        matches
        + disagreements
    )

    score_ab = (
        matches
        / b_size
    )

    score_ba = (
        matches
        / a_size
    )

    agreement = 0.0

    if shared > 0:

        agreement = (
            matches
            / shared
        )

    return (
        matches,
        disagreements,
        score_ab,
        score_ba,
        agreement
    )


def find_pairs(
    source_to_assertions
):

    source_ids = list(
        source_to_assertions.keys()
    )

    rows = []

    for i, source_a in enumerate(
        source_ids
    ):

        for source_b in source_ids[i + 1:]:

            a_assertions = source_to_assertions[
                source_a
            ]

            b_assertions = source_to_assertions[
                source_b
            ]

            (
                matches,
                disagreements,
                score_ab,
                score_ba,
                agreement
            ) = directional_inclusion(
                a_assertions,
                b_assertions
            )

            if (
                matches
                +
                disagreements
            ) == 0:

                continue

            asymmetry = abs(
                score_ab
                -
                score_ba
            )

            rows.append(
                (
                    asymmetry,
                    matches,
                    disagreements,
                    agreement,
                    source_a,
                    source_b,
                    len(a_assertions),
                    len(b_assertions),
                    score_ab,
                    score_ba
                )
            )

    rows.sort(
        reverse=True
    )

    return rows


def print_pairs(
    rows,
    source_names,
    n=30
):

    print()
    print("top directional inclusion pairs")
    print("-------------------------------")

    print(
        f"{'source_a':<25}"
        f"{'source_b':<25}"
        f"{'a_size':>8}  "
        f"{'b_size':>8}  "
        f"{'match':>7}  "
        f"{'diff':>6}  "
        f"{'D(A->B)':>10}  "
        f"{'D(B->A)':>10}  "
        f"{'agree':>8}  "
        f"{'asym':>8}"
    )

    for (
        asymmetry,
        matches,
        disagreements,
        agreement,
        source_a,
        source_b,
        a_size,
        b_size,
        score_ab,
        score_ba
    ) in rows[:n]:

        name_a = source_names.get(
            source_a,
            str(source_a)
        )

        name_b = source_names.get(
            source_b,
            str(source_b)
        )

        print(
            f"{name_a:<25}"
            f"{name_b:<25}"
            f"{a_size:>8}  "
            f"{b_size:>8}  "
            f"{matches:>7}  "
            f"{disagreements:>6}  "
            f"{score_ab:>10.3f}  "
            f"{score_ba:>10.3f}  "
            f"{agreement:>8.3f}  "
            f"{asymmetry:>8.3f}"
        )


def print_source_sizes(
    source_to_assertions,
    source_names
):

    rows = []

    for source_id, assertions in source_to_assertions.items():

        rows.append(
            (
                len(assertions),
                source_id
            )
        )

    rows.sort(
        reverse=True
    )

    print()
    print("source assertion counts")
    print("-----------------------")

    for count, source_id in rows:

        domain = source_names.get(
            source_id,
            str(source_id)
        )

        print(
            f"{domain:<25}"
            f"{count}"
        )


def main():

    print()
    print("loading sources...")

    source_names = load_sources()

    print()
    print("loading canonical assertions...")

    source_to_assertions = load_assertions()

    print_source_sizes(
        source_to_assertions,
        source_names
    )

    print()
    print("computing directional inclusion...")

    rows = find_pairs(
        source_to_assertions
    )

    print_pairs(
        rows,
        source_names
    )

    print()


if __name__ == "__main__":
    main()