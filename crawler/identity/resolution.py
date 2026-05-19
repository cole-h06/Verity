from identity.gtin import (
    normalize_gtin,
    gtin_similarity,
    longest_common_substring
)

from identity.model_matching import (
    find_existing_by_model
)


def resolve_product_identity(
    conn,
    gtin,
    model,
    sku,
    url,
    title,
    product,
    source_type
):
    existing = None

    if gtin:
        existing = conn.execute(
            "SELECT * FROM products WHERE gtin=?",
            (gtin,)
        ).fetchone()

    if not existing and model:
        existing = find_existing_by_model(conn, model)

    if existing:
        existing_id = existing["id"]

        print(
            f"[MATCHED PRODUCT ROW] "
            f"id={existing['id']} "
            f"gtin={existing['gtin']} "
            f"model={existing['model']}"
        )

        print("\n=== EXISTING PRODUCT FOUND ===")
        print("existing_id:", existing_id)
        print("existing_gtin:", existing["gtin"])

        json_ld_gtin = normalize_gtin(
            (
                product.get("gtin13")
                or product.get("gtin12")
                or product.get("gtin14")
                or product.get("gtin")
                or product.get("upc")
            ) if product else None
        )

        existing_gtin = normalize_gtin(existing["gtin"])

        if gtin:

            if not existing_gtin:
                print("\n=== GTIN BACKFILL ===")
                print("old_id:", existing_id)
                print("new_gtin:", gtin)

                conn.execute(
                    "UPDATE products SET gtin=? WHERE id=?",
                    (gtin, existing_id)
                )

                conn.execute("""
                    UPDATE raw_claims
                    SET product_id=?
                    WHERE product_id=?
                """, (gtin, existing["model"]))

            elif json_ld_gtin:

                similarity = gtin_similarity(gtin, existing_gtin)

                print(
                    f"[GTIN VERIFY] "
                    f"incoming={gtin} "
                    f"existing={existing_gtin} "
                    f"similarity={similarity:.2f}"
                )

                if similarity >= 0.95:

                    if gtin != existing_gtin:
                        print("\n=== JSON-LD GTIN VERIFIED ===")
                        print("old_gtin:", existing_gtin)
                        print("new_gtin:", gtin)

                else:
                    print(f"[IDENTITY REJECT] {url}")

                    conn.execute(
                        "DELETE FROM pending_crawl WHERE url=?",
                        (url,)
                    )

                    conn.commit()

                    return {
                        "should_skip": True
                    }

        elif source_type == "retailer":

            existing_title = (existing["title"] or "").lower()
            current_title = (title or "").lower()

            overlap = longest_common_substring(
                existing_title,
                current_title
            )

            similarity = overlap / max(
                len(existing_title),
                len(current_title),
                1
            )

            print(f"[TITLE VERIFY] similarity={similarity:.2f}")

            if similarity < 0.45:
                print(f"[IDENTITY REJECT - TITLE] {url}")

                conn.execute(
                    "DELETE FROM pending_crawl WHERE url=?",
                    (url,)
                )

                conn.commit()

                return {
                    "should_skip": True
                }

        record_id = gtin or existing_gtin or existing_id

    else:
        if gtin:
            record_id = gtin
        elif model:
            record_id = model
        elif sku:
            record_id = sku
        else:
            record_id = url

    return {
        "existing": existing,
        "record_id": record_id,
        "gtin": gtin,
        "model": model,
        "should_skip": False
    }