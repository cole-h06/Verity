from search_bridge import run_search_bridge
from db import mark_complete

from identity.gtin import (
    normalize_gtin
)


def pre_crawl(
    conn,
    existing_gtin,
    existing_model,
    linked_product,
    category,
    should_recrawl,
    url
):
    if not (existing_gtin or existing_model):
        return {
            "should_skip": False
        }

    print("[PRE-CRAWL SEARCH BRIDGE]")

    run_search_bridge(conn, {
        "gtin": existing_gtin,
        "model": existing_model,
        "sku": None,
        "brand": linked_product["brand"] if linked_product else None,
        "title": linked_product["title"] if linked_product else None,
        "price": None,
        "image_url": linked_product["image_url"] if linked_product else None,
        "category": category
    })

    resolved = conn.execute("""
        SELECT gtin, model
        FROM products
        WHERE
            gtin=?
            OR lower(model)=lower(?)
        LIMIT 1
    """, (
        existing_gtin,
        existing_model or ""
    )).fetchone()

    if resolved:

        resolved_gtin = normalize_gtin(
            resolved["gtin"]
        )

        resolved_model = resolved["model"]

        print("[PRE-CRAWL RESOLVED]")
        print("GTIN:", resolved_gtin)
        print("MODEL:", resolved_model)

        print("[IDENTITY COMPLETE - SKIPPING RECRAWL]")

        if (
            resolved_gtin
            and resolved_model
            and not should_recrawl
        ):

            print(
                "[SKIP FULL RECRAWL - "
                "SUFFICIENT DATA EXISTS]"
            )

            mark_complete(conn, url)

            return {
                "should_skip": True,
                "gtin": resolved_gtin,
                "model": resolved_model
            }

    return {
        "should_skip": False
    }