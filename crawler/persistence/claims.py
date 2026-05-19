from db import insert_claim


def persist_claims(
    conn,
    domain,
    crawl_id,
    record_id,
    structured
):
    row = conn.execute(
        "SELECT id FROM sources WHERE domain=?",
        (domain,)
    ).fetchone()

    if row:
        source_id = row["id"]
    else:
        cursor = conn.execute(
            """
            INSERT INTO sources
            (domain, brand, source_type, initial_reliability, learned_reliability, crawl_priority)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (domain, None, "unknown", 0.5, 0.5, 5)
        )

        source_id = cursor.lastrowid

    if not structured:
        return

    for attr, data in structured:

        if not isinstance(data, dict):
            display = str(data)
            math_val = str(data)
            unit = "text"

        else:
            display = data.get("display")
            math_val = data.get("math")
            unit = data.get("unit")

            if isinstance(math_val, dict):
                math_val = None

            if isinstance(math_val, str):
                if math_val.lower() in [
                    "not specified",
                    "n/a",
                    "unknown"
                ]:
                    math_val = None

        if display and str(display).lower() in [
            "not specified",
            "n/a",
            "unknown",
            ""
        ]:
            continue

        if attr == "upc":
            if display:
                display = str(display).replace(".0", "")

            math_val = None
            unit = "text"

        print(
            f"[INSERT] {attr} | {display} | "
            f"unit={unit} | math={math_val}"
        )

        insert_claim(
            conn,
            crawl_id,
            source_id,
            attr,
            display,
            product_id=record_id,
            unit=unit,
            value_numeric=math_val
        )