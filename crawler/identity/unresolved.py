from search_bridge import run_search_bridge

from db import (
    mark_unresolved,
    log_crawl,
    mark_complete
)

from identity.gtin import (
    normalize_gtin
)


def attempt_unresolved_resolution(
    conn,
    gtin,
    model,
    sku,
    brand,
    title,
    price,
    image_url,
    category,
    url,
    is_rebuild_mode
):
    if not gtin and not model:

        print(
            "[UNRESOLVED] "
            "Attempting immediate search bridge"
        )

        run_search_bridge(conn, {
            "gtin": gtin,
            "model": model,
            "sku": sku,
            "brand": brand,
            "title": title,
            "price": price,
            "image_url": image_url,
            "category": category
        })

        resolved = conn.execute("""
            SELECT gtin, model
            FROM products
            WHERE
                lower(title)=lower(?)
                OR (
                    model IS NOT NULL
                    AND lower(model)=lower(?)
                )
            LIMIT 1
        """, (
            title or "",
            model or ""
        )).fetchone()

        if resolved:

            gtin = normalize_gtin(
                resolved["gtin"]
            )

            model = resolved["model"]

            record_id = gtin or model

            print(
                f"[RESOLVED AFTER SEARCH] "
                f"GTIN={gtin} "
                f"MODEL={model}"
            )

            return {
                "resolved": True,
                "gtin": gtin,
                "model": model,
                "record_id": record_id
            }

        print(
            "[STILL UNRESOLVED] "
            "marking unresolved"
        )

        mark_unresolved(conn, url)

        return {
            "resolved": False
        }

    return {
        "resolved": True,
        "gtin": gtin,
        "model": model,
        "record_id": gtin or model
    }


def finalize_crawl_state(
    conn,
    gtin,
    model,
    sku,
    url,
    is_rebuild_mode
):
    if gtin and not is_rebuild_mode:

        conn.execute("""
            UPDATE raw_claims
            SET product_id=?
            WHERE product_id=?
               OR product_id=?
               OR product_id=?
        """, (
            gtin,
            url,
            model,
            sku
        ))

        conn.execute("""
            UPDATE raw_claims
            SET product_id=?
            WHERE page_id IN (
                SELECT id
                FROM crawled_pages
                WHERE url=?
            )
        """, (
            gtin,
            url
        ))

        print(
            f"[BACKFILL → GTIN] "
            f"{url} / {model} / {sku} → {gtin}"
        )

    if is_rebuild_mode:

        old_pages = conn.execute("""
            SELECT id
            FROM crawled_pages
            WHERE url=?
        """, (url,)).fetchall()

        for row in old_pages:

            print(
                f"[REBUILD DELETE] "
                f"old_page_id={row['id']}"
            )

            conn.execute("""
                DELETE FROM raw_claims
                WHERE page_id=?
            """, (row["id"],))

    crawl_id = log_crawl(
        conn,
        url,
        "success"
    )

    page_existing = conn.execute("""
        SELECT 1 FROM raw_claims
        WHERE page_id = ?
        LIMIT 1
    """, (crawl_id,)).fetchone()

    if page_existing and not is_rebuild_mode:

        print(
            f"[SKIP INSERT - "
            f"ALREADY PROCESSED PAGE] {url}"
        )

        mark_complete(conn, url)

        return {
            "should_skip": True,
            "crawl_id": crawl_id
        }

    return {
        "should_skip": False,
        "crawl_id": crawl_id
    }