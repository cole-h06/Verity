import json
from crawling.fetch_page import fetch_page
from brain import (
    process_product,
    get_pillar_count
)
from db import (
    get_db,
    mark_complete,
    mark_failed,
    log_crawl,
    count_claims,
    get_source_type
)
from persistence.claims import persist_claims
from identity.resolution import resolve_product_identity
from identity.gtin import normalize_gtin
from identity.extract_identity import enrich_identity
from identity.dedupe import (
    is_duplicate_sku
)
from identity.unresolved import (
    attempt_unresolved_resolution,
    finalize_crawl_state
)
from extraction.product_data import extract_product_data
from extraction.home_depot import (
    extract_home_depot_specs
)
from search.discovery import pre_crawl_search_bridge
from search.post_identity import (
    run_post_identity_enrichment
)
from search.second_pass import (
    run_second_pass_discovery
)
from config import (
    IDENTITY_RESET_MODE,
    REBUILD_MODE
)


from extraction.identity_extractors import (
    extract_sku_from_text
)


from identity.model_matching import (
    is_valid_model
)


MIN_CLAIMS = 10

IDENTITY_FIELDS = {
    "gtin",
    "model",
    "sku",
    "mpn",
    "upc",
    "dpci",
    "model_number"
}


def lookup_existing_product(conn, url):
    page_row = conn.execute("""
        SELECT id
        FROM crawled_pages
        WHERE url=?
        ORDER BY id DESC
        LIMIT 1
    """, (url,)).fetchone()

    page_id = page_row["id"] if page_row else None

    product_id = None

    if page_id:
        linked_claim = conn.execute("""
            SELECT product_id
            FROM raw_claims
            WHERE page_id=?
              AND product_id IS NOT NULL
              AND product_id != ''
            LIMIT 1
        """, (page_id,)).fetchone()

        if linked_claim:
            product_id = linked_claim["product_id"]

    existing_product = None

    if product_id:
        existing_product = conn.execute("""
            SELECT *
            FROM products
            WHERE gtin=?
               OR lower(model)=lower(?)
            LIMIT 1
        """, (
            product_id,
            product_id
        )).fetchone()

    existing_gtin = None
    existing_model = None

    if existing_product:
        existing_gtin = normalize_gtin(
            existing_product["gtin"]
        )

        if is_valid_model(
            existing_product["model"]
        ):
            existing_model = existing_product["model"]

    return (
        product_id,
        existing_product,
        existing_gtin,
        existing_model
    )


def get_gtin(combined_specs):
    for name, value in combined_specs:
        if str(name).lower() not in {"gtin", "upc"}:
            continue

        value = str(value).strip()

        if value.isdigit() and 12 <= len(value) <= 14:
            print(f"[FINAL GTIN] {value}")
            return value

    return None


def add_additional_properties(product, combined_specs):
    if not product:
        return

    for prop in product.get("additionalProperty", []):
        name = prop.get("name")
        value = prop.get("value")

        if name and value:
            combined_specs.append((name, value))


def strip_identity_claims(structured):
    filtered = []

    for attr, data in structured:
        if attr in {
            "gtin",
            "model",
            "sku",
            "mpn",
            "upc",
            "dpci",
            "model_number"
        }:
            print(f"[POST-FILTER REMOVED] {attr}: {data}")
            continue

        filtered.append((attr, data))

    return filtered


def fill_missing_metadata(structured, brand, title):
    for attr, data in structured:

        if not isinstance(data, dict):
            continue

        display = data.get("display")

        if not display:
            continue

        if attr == "brand" and not brand:
            brand = display

        elif attr in {"title", "product_name"} and not title:
            title = display

    return brand, title


async def run_miner(url, category):
    conn = get_db()

    print("\n" + "="*80)
    print(f"[MINER START] {url}")
    print(f"[CATEGORY] {category}")
    print("="*80)

    status_row = conn.execute(
        "SELECT status FROM pending_crawl WHERE url=?",
        (url,)
    ).fetchone()
 
    status = status_row["status"] if status_row else "pending"

    product_id, existing_product, existing_gtin, existing_model = (
        lookup_existing_product(conn, url)
    )
 
    need_identity = not (
        existing_gtin or existing_model
    )

    claim_count = count_claims(
        conn,
        product_id
    )

    rebuild_specs = (
        claim_count < MIN_CLAIMS
    )

    print("claim_count:", claim_count)
    print("rebuild_specs:", rebuild_specs)

    identity_mode = (
        IDENTITY_RESET_MODE
        and need_identity
    )

    print("[IDENTITY]", existing_gtin, existing_model)
    recrawl = (
        need_identity
        or rebuild_specs
    )

    print("\n=== RECRAWL CHECK ===")
    print("need_identity:", need_identity)
    print("rebuild_specs:", rebuild_specs)
    print("recrawl:", recrawl)
 
    rebuild_mode = (
        REBUILD_MODE and recrawl
    )

    if rebuild_mode:
        print("[MODE] REBUILD")
    elif identity_mode:
        print("[MODE] IDENTITY")
    else:
        print("[MODE] NORMAL")

    if status == "failed" and not rebuild_mode:
        print(f"[SKIP FAILED] {url}")
        conn.close()
        return {"skipped": True}

    if ".pdf" in url.lower():
        print(f"[SKIP PDF] {url}")
        mark_complete(conn, url)
        conn.commit()
        conn.close()
        return {"skipped": True}

    pre_result = pre_crawl_search_bridge(
        conn=conn,
        existing_gtin=existing_gtin,
        existing_model=existing_model,
        existing_product=existing_product,
        category=category,
        recrawl=recrawl,
        url=url
    )

    if pre_result["should_skip"]:
        return {
            "gtin": pre_result["gtin"],
            "model": pre_result["model"],
            "skipped": True
        }

    try:
        crawl_result = await fetch_page(url)

        html = crawl_result["html"]
        markdown = crawl_result["markdown"]
        next_specs = crawl_result["next_specs"]
        generic_specs = crawl_result["generic_specs"]
        extracted_specs = crawl_result["extracted_specs"]
        spec_payloads = crawl_result["spec_payloads"]
        domain = crawl_result["domain"]

        print("\n===== MARKDOWN LENGTH =====")
        print(len(markdown))

        extracted_specs = extract_home_depot_specs(
            spec_payloads
        )

        if extracted_specs:
            print("\n===== API SPECS =====")
            print(extracted_specs[:10])

        product_data = extract_product_data(
            html=html,
            extracted_specs=extracted_specs,
            next_specs=next_specs,
            generic_specs=generic_specs
        )

        product = product_data["product"]
        combined_specs = product_data["combined_specs"]

        title = product_data["title"]
        brand = product_data["brand"]
        gtin = product_data["gtin"]
        sku = product_data["sku"]
        model = product_data["model"]
        price = product_data["price"]
        image_url = product_data["image_url"]

        identity = {
            "gtin": gtin,
            "model": model,
            "sku": sku,
            "dpci": None
        }

        result = enrich_identity(
            identity=identity,
            html=html,
            markdown=markdown,
            product=product,
            next_specs=next_specs,
            combined_specs=combined_specs,
            domain=domain
        )

        identity = result["identity"]
        combined_specs = result["combined_specs"]

        if not identity["gtin"]:
            identity["gtin"] = get_gtin(
                combined_specs
            )

        add_additional_properties(
            product,
            combined_specs
        )

        print("\n=== DEBUG: BEFORE process_product ===")
        print("combined_specs len:", len(combined_specs))
        print("markdown len:", len(markdown) if markdown else 0)
        print("product exists:", bool(product))

        if identity_mode and not rebuild_mode:
            print("[UNRESOLVED] skipping spec extraction")
            structured = []

        else:
            structured_input = [
                {
                    "source_label": name,
                    "source_value": value
                }
                for name, value in combined_specs
            ] if combined_specs else None

            print(
                f"[PROCESS_PRODUCT INPUT] combined_specs={len(combined_specs)} "
                f"structured_input={len(structured_input or [])} "
                f"skip_llm={False if rebuild_mode else bool(structured_input)}"
            )

            structured = process_product(
                product_json=product,
                markdown=markdown,
                category=category,
                skip_llm=False if rebuild_mode else bool(structured_input),
                structured_input=structured_input
            )

            structured = list(structured or [])


        print("\n=== DEBUG: AFTER process_product ===")
        print("structured len:", len(structured))
        print("structured sample:", structured[:5])

        print("\n=== FINAL STRUCTURED CLAIMS ===")
        for attr, data in structured[:15]:
            print(attr, "=>", data)

        structured = strip_identity_claims(
            structured
        )

        print(f"[POST FILTER CLAIM COUNT] {len(structured)}")

        brand, title = fill_missing_metadata(
            structured,
            brand,
            title
        )

        gtin = normalize_gtin(identity["gtin"])
        model = identity["model"]
        sku = identity["sku"]

        if not sku:
            sku = extract_sku_from_text(markdown, html)

        if not rebuild_mode and is_duplicate_sku(conn, domain, sku):
            print(f"[DEDUP SKIP] {domain} | SKU={sku} | URL={url}")

            mark_complete(conn, url)

            return {"skipped": True}

        source_type = get_source_type(conn, url)
        pillar_count = get_pillar_count(structured, category)

        print("\n=== DEBUG: FILTER CHECK ===")
        print("source_type:", source_type)
        print("pillar_count:", pillar_count)

        resolution = resolve_product_identity(
            conn=conn,
            gtin=gtin,
            model=model,
            sku=sku,
            url=url,
            title=title,
            product=product,
            source_type=source_type
        )

        if resolution["should_skip"]:
            return {"skipped": True}

        existing = resolution["existing"]
        record_id = resolution["record_id"]
        gtin = resolution["gtin"]
        model = resolution["model"]

        print("\n=== FINAL IDENTITY ===")
        print("GTIN:", gtin)
        print("MODEL:", model)
        print("SKU:", sku)
        print("BRAND:", brand)
        print("TITLE:", title)
        print("RECORD ID:", record_id)

        if gtin and model:
            conn.execute("""
                UPDATE products
                SET gtin=?
                WHERE model=? AND (gtin IS NULL OR gtin='')
            """, (gtin, model))

            print(f"[PRODUCT GTIN BACKFILL] {model} → {gtin}")

        print(f"[UNRESOLVED CHECK] gtin={gtin} model={model} sku={sku}")

        unresolved_result = attempt_unresolved_resolution(
            conn=conn,
            gtin=gtin,
            model=model,
            sku=sku,
            brand=brand,
            title=title,
            price=price,
            image_url=image_url,
            category=category,
            url=url
        )

        if unresolved_result["resolved"]:
            gtin = unresolved_result["gtin"]
            model = unresolved_result["model"]
            record_id = unresolved_result["record_id"]
        else:
            return {"skipped": True}

        finalize_result = finalize_crawl_state(
            conn=conn,
            gtin=gtin,
            model=model,
            sku=sku,
            url=url,
            rebuild_mode=rebuild_mode
        )

        crawl_id = finalize_result["crawl_id"]

        if finalize_result["should_skip"]:
            return {"skipped": True}

        persist_claims(
            conn=conn,
            domain=domain,
            crawl_id=crawl_id,
            record_id=record_id,
            structured=structured
        )

        run_post_identity_enrichment(
            conn=conn,
            existing=existing,
            gtin=gtin,
            model=model,
            sku=sku,
            brand=brand,
            title=title,
            price=price,
            image_url=image_url,
            category=category,
            domain=domain,
            url=url,
            product=product,
            next_specs=next_specs
        )

        if identity_mode and not rebuild_mode:
            print("[GTIN BEFORE SEARCH BRIDGE]:", gtin)
            print("\n=== TRIGGER SEARCH BRIDGE ===")

        print("\n" + "="*80)
        print(f"[MINER COMPLETE] {url}")
        print(f"[FINAL GTIN] {gtin}")
        print(f"[FINAL MODEL] {model}")
        print(f"[CLAIMS INSERTED] {len(structured)}")
        print("="*80)

        if identity_mode and (gtin or model) and not rebuild_mode:
            return run_second_pass_discovery(
                conn=conn,
                gtin=gtin,
                model=model,
                sku=sku,
                brand=brand,
                title=title,
                price=price,
                image_url=image_url,
                category=category,
                url=url
            )

        return {
            "gtin": gtin,
            "model": model,
            "needs_enrichment": not (gtin and model)
        }

    except Exception:
        import traceback
        traceback.print_exc()
        log_crawl(conn, url, "failed")
        mark_failed(conn, url)
        return None

    finally:
        conn.commit()
        conn.close()
