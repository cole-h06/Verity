import re
import httpx
from urllib.parse import urlparse
from serper import serper_search
from db import save_url, upsert_product

BINARY_EXTENSIONS = {
    ".csv", ".xlsx", ".xls", ".pdf", ".zip", ".rar", ".gz",
    ".doc", ".docx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".mp4", ".mp3"
}

RETAILER_SITES = (
    "site:amazon.com OR "
    "site:walmart.com OR "
    "site:target.com OR "
    "site:bestbuy.com OR "
    "site:homedepot.com OR "
    "site:lowes.com OR "
    "site:costco.com OR "
    "site:macys.com OR "
    "site:kohls.com OR "
    "site:bjs.com OR "
    "site:samsclub.com OR "
    "site:bhphotovideo.com OR "
    "site:newegg.com OR "
    "site:microcenter.com OR "
    "site:ajmadison.com OR "
    "site:pcrichard.com OR "
    "site:wayfair.com"
)

def has_binary_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in BINARY_EXTENSIONS)


def is_html_via_head(url: str) -> bool:
    try:
        r = httpx.head(
            url,
            follow_redirects=True,
            timeout=5,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            }
        )

        content_type = r.headers.get("content-type", "").lower()

        print(f"[HEAD CHECK] {url}")
        print(f"[HEAD STATUS] {r.status_code}")
        print(f"[HEAD CONTENT TYPE] {content_type}")

        if "text/html" in content_type:
            return True

        print("[HEAD FALLBACK GET]")

        r = httpx.get(
            url,
            follow_redirects=True,
            timeout=10,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            }
        )

        content_type = r.headers.get("content-type", "").lower()

        print(f"[GET STATUS] {r.status_code}")
        print(f"[GET CONTENT TYPE] {content_type}")

        return "text/html" in content_type

    except Exception as e:
        print(f"[HEAD CHECK ERROR] {url} -> {e}")
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


def normalize_gtin(gtin):
    if not gtin:
        return None

    gtin = str(gtin)

    digits = re.sub(r"\D", "", gtin)

    if not digits:
        return None

    digits = digits.lstrip("0")

    return digits


def normalize_model(model):
    if not model:
        return None

    model = str(model).upper()

    model = re.sub(r"[^A-Z0-9]", "", model)

    return model


def longest_common_substring(a, b):
    if not a or not b:
        return 0

    m = [[0] * (1 + len(b)) for _ in range(1 + len(a))]

    longest = 0

    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                m[i][j] = m[i - 1][j - 1] + 1
                longest = max(longest, m[i][j])

    return longest


def gtin_overlap_score(seed_gtin, candidate_gtin):
    seed_gtin = normalize_gtin(seed_gtin)
    candidate_gtin = normalize_gtin(candidate_gtin)

    if not seed_gtin or not candidate_gtin:
        return 0

    if seed_gtin == candidate_gtin:
        return 1.0

    overlap = longest_common_substring(seed_gtin, candidate_gtin)

    score = overlap / max(len(seed_gtin), len(candidate_gtin))

    return score


def model_overlap_score(seed_model, candidate_model):
    seed_model = normalize_model(seed_model)
    candidate_model = normalize_model(candidate_model)

    if not seed_model or not candidate_model:
        return 0

    if seed_model == candidate_model:
        return 1.0

    overlap = longest_common_substring(seed_model, candidate_model)

    score = overlap / max(len(seed_model), len(candidate_model))

    return score


def fetch_html_title(url):
    try:
        r = httpx.get(
            url,
            follow_redirects=True,
            timeout=10,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                )
            }
        )

        html = r.text

        h1_match = re.search(
            r"<h1[^>]*>(.*?)</h1>",
            html,
            re.I | re.S
        )

        if h1_match:
            title = re.sub(
                r"<.*?>",
                "",
                h1_match.group(1)
            )

            title = re.sub(r"\s+", " ", title).strip()

            print(f"[H1 TITLE] {title}")

            return title

        title_match = re.search(
            r"<title>(.*?)</title>",
            html,
            re.I | re.S
        )

        if title_match:
            title = re.sub(
                r"\s+",
                " ",
                title_match.group(1)
            ).strip()

            print(f"[HTML TITLE] {title}")

            return title

        print(f"[TITLE NOT FOUND] {url}")

        return None

    except Exception as e:
        print(f"[TITLE FETCH ERROR] {url} -> {e}")
        return None


def identity_matches(seed_product, candidate_product):
    seed_gtin = seed_product.get("gtin")
    candidate_gtin = candidate_product.get("gtin")

    seed_model = seed_product.get("model")
    candidate_model = candidate_product.get("model")

    print("\n[IDENTITY CHECK]")
    print(f"SEED GTIN: {seed_gtin}")
    print(f"CANDIDATE GTIN: {candidate_gtin}")
    print(f"SEED MODEL: {seed_model}")
    print(f"CANDIDATE MODEL: {candidate_model}")

    if seed_gtin and candidate_gtin:
        gtin_score = gtin_overlap_score(seed_gtin, candidate_gtin)

        print(f"[GTIN SCORE] {gtin_score}")

        if gtin_score >= 0.85:
            print("[IDENTITY PASS] GTIN match")
            return True

        print("[IDENTITY FAIL] GTIN mismatch")
        return False

    if seed_model and candidate_model:
        model_score = model_overlap_score(seed_model, candidate_model)

        print(f"[MODEL SCORE] {model_score}")

        if model_score >= 0.70:
            print("[IDENTITY PASS] MODEL match")
            return True

        print("[IDENTITY FAIL] MODEL mismatch")
        return False

    print("[IDENTITY UNKNOWN] Missing comparable identifiers")
    return True


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


def get_manufacturer_domain(conn, brand):
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

    clean_title = None

    if title:
        clean_title = re.sub(r"[^\w\s\-]", " ", title)
        clean_title = re.sub(r"\s+", " ", clean_title).strip()
 
    if gtin:
        queries.append((
            "serper",
            f'"{gtin}" ({RETAILER_SITES})',
            "gtin"
        )) 

    if clean_title:
        queries.append((
            "serper",
            f'"{clean_title}" ({RETAILER_SITES})',
            "title"
        ))

    if model:
        queries.append((
            "serper",
            f'{model} ({RETAILER_SITES})',
            "model"
        ))

    if model:
        domain =  get_manufacturer_domain(conn, brand) if conn else None
        print(f"[BUILD QUERIES] Manufacturer domain candidate: {domain}")

        if domain:
                queries.append(("serper", f'site:{domain} {model} specs', "model"))

        if domain and clean_title:
            queries.append((
                "serper",
                f'site:{domain} "{clean_title}"',
                "title"
            ))

        if model:
            queries.append(("serper", f'site:energystar.gov/productfinder {model}', "model"))

        if category == "laptops":
            queries.append(("serper", f'site:fccid.io "{model}"', "model"))

    print(f"[BUILD QUERIES OUTPUT] Total queries: {len(queries)}")
    for q in queries:
        print(f"  {q}")

    return queries


def product_key(product):
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
            print(f"[SEARCH ERROR] {provider} | {query} -> {e}")

    print(f"[RUN BATCH] Unique results: {len(results)}")
    return results


def run_discovery(conn, product):
    upsert_product(conn, product)

    print("\n[DISCOVERY]")
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
        print(f"[SKIP] already searched: {search_key}")
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
    title_queries = []
    brand_gtin = []
    brand_model = []
    brand_sku = []
    other_queries = []

    for provider, query, qtype in queries:
        if qtype == "gtin":
            gtin_queries.append((provider, query))
        elif qtype == "model":
            model_queries.append((provider, query))
        elif qtype == "title":
            title_queries.append((provider, query))
        elif qtype == "brand_gtin":
            brand_gtin.append((provider, query))
        elif qtype == "brand_model":
            brand_model.append((provider, query))
        elif qtype == "brand_sku":
            brand_sku.append((provider, query))
        else:
            other_queries.append((provider, query))

    print(
        f"queries: gtin={len(gtin_queries)} "
        f"model={len(model_queries)} "
        f"title={len(title_queries)}"
    )

    all_results = []

    def run_queries(query_list):
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
                print(f"[SEARCH ERROR] {provider} | {query} -> {e}")
        print(f"[RUN BATCH WITH PROVIDER] Result pairs: {len(results)}")
        return results

    all_results.extend(run_queries(gtin_queries))
    all_results.extend(run_queries(model_queries))
    all_results.extend(run_queries(title_queries))

    brand_results = []

    if brand_gtin:
        print("[BRAND PHASE] Running brand_gtin queries")
        brand_results = run_queries(brand_gtin)

    if not brand_results and brand_model:
        print("[BRAND PHASE] No brand_gtin hits, running brand_model queries")
        brand_results = run_queries(brand_model)

    if not brand_results and brand_sku:
        print("[BRAND PHASE] No brand_model hits, running brand_sku queries")
        brand_results = run_queries(brand_sku)

    all_results.extend(brand_results)
    all_results.extend(run_queries(other_queries))

    print(f"\n[RAW RESULTS COUNT]: {len(all_results)}")

    seen_urls = set()
    domain_counts = {}

    structured_identity = bool(
        product.get("gtin")
        or product.get("model")
    )

    if structured_identity:
        MAX_URLS_PER_DOMAIN = 3
        print("structured identity found")
    else:
        MAX_URLS_PER_DOMAIN = 1
        print("no structured identity")

    seed_url = product.get("source_url")

    for url, provider in all_results:

        if url in seen_urls:
            continue

        if seed_url and url == seed_url:
            print(f"[FILTER SKIP] Seed URL: {url}")
            continue

        already_crawled = conn.execute(
            "SELECT 1 FROM crawled_pages WHERE url=? LIMIT 1",
            (url,)
        ).fetchone()

        if already_crawled:
            print(f"[FILTER SKIP] Already crawled URL: {url}")
            continue

        already_pending = conn.execute(
            "SELECT 1 FROM pending_crawl WHERE url=? LIMIT 1",
            (url,)
        ).fetchone()
 
        if already_pending:
            print(f"[FILTER SKIP] Already pending URL: {url}")
            continue
  
        if not is_crawlable(url):
            continue

        domain = extract_domain(url)

        is_manufacturer = domain == get_manufacturer_domain(
            conn,
            product.get("brand")
        )

        if not structured_identity and not is_manufacturer:

            candidate_title = fetch_html_title(url)

            if candidate_title:

                seed_title = product.get("title", "")

                overlap = longest_common_substring(
                    seed_title.lower(),
                    candidate_title.lower()
                )

                similarity = overlap / max(
                    len(seed_title),
                    len(candidate_title)
                )

                print(f"[TITLE SIMILARITY] {similarity}")

                if similarity < 0.45:
                    print(f"[FILTER SKIP] Title mismatch: {url}")
                    continue

        if not domain:
            print(f"[FILTER SKIP] No domain: {url}")
            continue

        if domain in existing_domains:
            print(f"[FILTER SKIP] Existing domain already covered: {domain} | {url}")
            continue

        current_count = domain_counts.get(domain, 0)

        domain_limit = (
            1 if is_manufacturer
            else MAX_URLS_PER_DOMAIN
        )

        if current_count >= domain_limit:

            if MAX_URLS_PER_DOMAIN == 1:
                print(
                    f"[FILTER SKIP] Single URL mode already satisfied: "
                    f"{domain} | {url}"
                )
            else:
                print(
                    f"[FILTER SKIP] Multi URL limit reached: "
                    f"{domain} | {url}"
                )

            continue

        domain_counts[domain] = current_count + 1

        seen_urls.add(url)

        priority = get_crawl_priority(conn, url)

        print(
            f"[FILTER PASS] {url} | "
            f"provider={provider} | "
            f"priority={priority} | "
            f"domain_count={domain_counts[domain]}"
        )

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
    print(f"\nsaved {len(seen_urls)} urls\n")