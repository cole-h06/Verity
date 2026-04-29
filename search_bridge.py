import re
import httpx
from urllib.parse import urlparse
from search import serper_search
from db import save_url, upsert_product

BINARY_EXTENSIONS = {
    ".csv", ".xlsx", ".xls", ".pdf", ".zip", ".rar", ".gz",
    ".doc", ".docx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mp3"
}

def has_binary_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in BINARY_EXTENSIONS)


def is_html_via_head(url: str) -> bool:
    try:
        r = httpx.head(url, follow_redirects=True, timeout=5)
        content_type = r.headers.get("content-type", "").lower()
        return "text/html" in content_type
    except Exception:
        return False


def is_crawlable(url: str) -> bool:
    if has_binary_extension(url):
        print(f"[FILTER SKIP] Binary extension: {url}")
        return False

    last_segment = urlparse(url).path.split("/")[-1]

    if "." not in last_segment:
        if not is_html_via_head(url):
            print(f"[FILTER SKIP] Non-HTML via HEAD: {url}")
            return False

    return True


def extract_domain(url):
    try:
        domain = urlparse(url).netloc.lower().replace("www.", "")
        parts = domain.split(".")

        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return domain
    except:
        return None


def get_crawl_priority(conn, url):
    domain = extract_domain(url)
    print(f"[PRIORITY LOOKUP] URL: {url} | DOMAIN: {domain}")

    if not domain:
        print("[PRIORITY LOOKUP] No domain, using default 5")
        return 5

    row = conn.execute(
        "SELECT crawl_priority FROM sources WHERE domain=?",
        (domain,)
    ).fetchone()

    if row:
        print(f"[PRIORITY LOOKUP] Existing priority for {domain}: {row['crawl_priority']}")
        return row["crawl_priority"]

    if "reddit.com" in domain or "forum" in domain:
        default_prior = 0.20
        default_priority = 3
        source_type = "forum"
    else:
        default_prior = 0.15
        default_priority = 2
        source_type = "other"

    conn.execute(
        """
        INSERT OR IGNORE INTO sources
        (domain, brand, source_type, initial_reliability, learned_reliability, crawl_priority)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (domain, None, source_type, default_prior, default_prior, default_priority)
    )

    print(f"[PRIORITY LOOKUP] Inserted new source {domain} | type={source_type} | priority={default_priority}")
    return default_priority


def get_mfr_domain(conn, brand):
    print(f"[MFR DOMAIN INPUT] RAW BRAND: {brand}")
    
    if not brand:
        print("[MFR DOMAIN] No brand provided")
        return None

    brand_key = re.sub(r"[^a-z0-9]", "", brand.lower())
    print(f"[MFR DOMAIN INPUT] NORMALIZED BRAND: {brand_key}")

    row = conn.execute(
        """
        SELECT domain FROM sources
        WHERE source_type='manufacturer'
        AND LOWER(brand)=LOWER(?)
        LIMIT 1
        """,
        (brand_key,)
    ).fetchone()

    if row:
        print(f"[MFR DOMAIN] Found manufacturer domain: {row['domain']}")
        return row["domain"]

    print("[MFR DOMAIN] No manufacturer domain found")
    return None


def build_queries(gtin=None, model=None, brand=None, title=None, conn=None, category=None):
    queries = []

    print("\n[BUILD QUERIES INPUT]")
    print(f"  GTIN: {gtin}")
    print(f"  Model: {model}")
    print(f"  Brand: {brand}")
    print(f"  Title: {title}")
    print(f"  Category: {category}")

    if gtin:
        queries.append((
            "serper",
            f'"{gtin}" (site:amazon.com OR site:walmart.com OR site:target.com OR site:bestbuy.com OR site:homedepot.com OR site:lowes.com)',
            "gtin"
        ))

        queries.append((
            "serper",
            f'"{gtin}" (site:bhphotovideo.com OR site:newegg.com OR site:microcenter.com)',
            "gtin"
        ))

    if model and brand:
        domain = get_mfr_domain(conn, brand) if conn else None
        print(f"[BUILD QUERIES] Manufacturer domain candidate: {domain}")

        if domain:
            if gtin:
                queries.append(("serper", f'site:{domain} "{gtin}"', "brand_gtin"))

            if model:
                queries.append(("serper", f'site:{domain} "{model}"', "brand_model"))

        if gtin and model:
            queries.append(("serper", f'site:energystar.gov/productfinder "{gtin}"', "model"))
            queries.append(("serper", f'site:energystar.gov/productfinder "{model}"', "model"))

        if category == "laptops":
            queries.append(("serper", f'site:fccid.io "{model}"', "model"))

    print(f"[BUILD QUERIES OUTPUT] Total queries: {len(queries)}")
    for q in queries:
        print(f"  {q}")

    return queries


def build_search_key(product):
    search_key = (
        product.get("gtin")
        or product.get("model")
        or (product.get("brand", "") + product.get("title", ""))
    )
    print(f"[SEARCH KEY] {search_key}")
    return search_key


def run_batch(query_list):
    results = set()
    print(f"[RUN BATCH] Query count: {len(query_list)}")

    for provider, query in query_list:
        print(f"\n[SEARCH] {provider.upper()} -> {query}")
        try:
            if provider == "serper":
                urls = serper_search(query)
            else:
                continue
            print(f"[SEARCH RESULT COUNT] {len(urls)}")
            results.update(urls)
        except Exception as e:
            print(f"[SEARCH BRIDGE ERROR] {provider} | {query} -> {e}")

    print(f"[RUN BATCH] Unique results: {len(results)}")
    return results


def run_search_bridge(conn, product):
    upsert_product(conn, product)

    print("\n[SEARCH BRIDGE START]")
    print(f"  GTIN: {product.get('gtin')}")
    print(f"  Model: {product.get('model')}")
    print(f"  SKU: {product.get('sku')}")
    print(f"  Brand: {product.get('brand')}")
    print(f"  Title: {product.get('title')}")
    print(f"  Category: {product.get('category')}")
    print(f"  Price: {product.get('price')}")
    print(f"  Image URL: {product.get('image_url')}")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS searched_products (
        key TEXT PRIMARY KEY
    )
    """)

    search_key = build_search_key(product)

    already = conn.execute(
        "SELECT 1 FROM searched_products WHERE key=?",
        (search_key,)
    ).fetchone()

    if already:
        print(f"[SEARCH BRIDGE SKIP] already searched: {search_key}")
        return

    existing_domains = set()

    if product.get("gtin"):
        rows = conn.execute(
            """
            SELECT DISTINCT s.domain
            FROM raw_claims rc
            JOIN sources s ON rc.source_id = s.id
            WHERE rc.product_id=?
            """,
            (product.get("gtin"),)
        ).fetchall()

        for r in rows:
            domain = r[0]
            if domain:
                existing_domains.add(domain)

    print(f"[EXISTING DOMAINS] {sorted(existing_domains)}")

    queries = build_queries(
        gtin=product.get("gtin"),
        model=product.get("model"),
        brand=product.get("brand"),
        title=product.get("title"),
        conn=conn,
        category=product.get("category")
    )

    print("\n[SEARCH QUERIES]")
    for q in queries:
        print(f"  {q}")

    gtin_queries = []
    model_queries = []
    brand_gtin = []
    brand_model = []
    brand_sku = []
    other_queries = []

    for provider, query, qtype in queries:
        if qtype == "gtin":
            gtin_queries.append((provider, query))
        elif qtype == "model":
            model_queries.append((provider, query))
        elif qtype == "brand_gtin":
            brand_gtin.append((provider, query))
        elif qtype == "brand_model":
            brand_model.append((provider, query))
        elif qtype == "brand_sku":
            brand_sku.append((provider, query))
        else:
            other_queries.append((provider, query))

    print(f"[QUERY BUCKETS] gtin={len(gtin_queries)} model={len(model_queries)} brand_gtin={len(brand_gtin)} brand_model={len(brand_model)} brand_sku={len(brand_sku)} other={len(other_queries)}")

    all_results = []

    def run_batch_with_provider(query_list):
        results = []
        print(f"[RUN BATCH WITH PROVIDER] Query count: {len(query_list)}")
        for provider, query in query_list:
            print(f"\n[SEARCH] {provider.upper()} -> {query}")
            try:
                if provider == "serper":
                    urls = serper_search(query)
                else:
                    continue

                print(f"[SEARCH RESULT COUNT] {len(urls)}")

                for u in urls:
                    print(f"  [FOUND] {u}")
                    results.append((u, provider))
            except Exception as e:
                print(f"[SEARCH BRIDGE ERROR] {provider} | {query} -> {e}")
        print(f"[RUN BATCH WITH PROVIDER] Result pairs: {len(results)}")
        return results

    all_results.extend(run_batch_with_provider(gtin_queries))
    all_results.extend(run_batch_with_provider(model_queries))

    brand_results = []

    if brand_gtin:
        print("[BRAND PHASE] Running brand_gtin queries")
        brand_results = run_batch_with_provider(brand_gtin)

    if not brand_results and brand_model:
        print("[BRAND PHASE] No brand_gtin hits, running brand_model queries")
        brand_results = run_batch_with_provider(brand_model)

    if not brand_results and brand_sku:
        print("[BRAND PHASE] No brand_model hits, running brand_sku queries")
        brand_results = run_batch_with_provider(brand_sku)

    all_results.extend(brand_results)
    all_results.extend(run_batch_with_provider(other_queries))

    print(f"\n[RAW RESULTS COUNT]: {len(all_results)}")

    seen_urls = set()
    seen_domains = set()

    for url, provider in all_results:
        if url in seen_urls:
            print(f"[FILTER SKIP] Duplicate URL: {url}")
            continue

        if not is_crawlable(url):
            continue

        domain = extract_domain(url)
        if not domain:
            print(f"[FILTER SKIP] No domain: {url}")
            continue

        if domain in existing_domains:
            print(f"[FILTER SKIP] Existing domain already covered: {domain} | {url}")
            continue

        if domain in seen_domains:
            print(f"[FILTER SKIP] Domain already added in this batch: {domain} | {url}")
            continue

        seen_urls.add(url)
        seen_domains.add(domain)

        priority = get_crawl_priority(conn, url)

        print(f"[FILTER PASS] {url} | provider={provider} | priority={priority}")

        save_url(
            conn,
            url,
            category=product.get("category"),
            priority=priority,
            provider=provider
        )

        print(f"[SAVED] {url}")

    conn.execute(
        "INSERT OR IGNORE INTO searched_products (key) VALUES (?)",
        (search_key,)
    )
    conn.commit()

    print(f"[SEARCHED MARKED] {search_key}")
    print(f"\n[SEARCH BRIDGE END] Saved: {len(seen_urls)} URLs\n")