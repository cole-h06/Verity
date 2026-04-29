from __future__ import annotations

import os
import re
import json
import requests
import time
import random
import hashlib
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
from collections import deque
from threading import Thread
from post_processing import analyze_product

from config import (
    SEED_URLS,
    SITEMAP_URLS,
    DEV_CRAWL_LIMIT,
    USER_AGENT,
    TIMEOUT_S,
    SNAPSHOT_DIR,
    PRIORS_BY_TYPE,
    BRAVE_API_KEY,
    DISCOVERY_MODE,
)

from db import (
    initialize_database,
    get_db,
    get_domain,
    lookup_source_type_and_prior,
    upsert_source,
    utcnow_iso,
    resolve_missing_identity,
)

from frontier import (
    get_next_frontier_url,
    mark_frontier_complete,
    mark_frontier_failed,
    reset_frontier_pending
)

from crawl_core import save_gz_text
from crawler_parser import parse_page, extract_visible_text, run_llm, safe_json_parse
from playwright.sync_api import sync_playwright

last_request_time = {}

def rate_limit(domain):
    now = time.time()
    last = last_request_time.get(domain, 0)

    delay = random.uniform(3, 8)

    if now - last < delay:
        time.sleep(delay - (now - last))

    last_request_time[domain] = time.time()

def human_delay(page, min_ms=1500, max_ms=5000):
    page.wait_for_timeout(random.randint(min_ms, max_ms))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "knowledge_graph.db")

retry_counts = {}
MAX_RETRIES = 3
current_model = None

def insert_raw_specs(conn, url, domain, html_sha, html_path, parsed):

    identity = parsed.get("identity", {})
    claims = parsed.get("claims", [])

    brand = identity.get("brand")
    model = identity.get("model")
    title = identity.get("title")

    brand, model = resolve_missing_identity(
        conn,
        identity.get("brand"),
        identity.get("model"),
        identity.get("title")
    )

    identity["brand"] = brand
    identity["model"] = model

    if not valid_model(model):
        print("[NO MODEL — STORING PARTIAL DATA]")

    if model and not model_exists(conn, model):

        conn.execute(
            """
            INSERT INTO crawl_products (model, brand, title)
            VALUES (?, ?, ?)
            """,
            (
                model,
                brand,
                title
            )
        )

        print(f"[NEW PRODUCT INSERTED] {brand} {model}")

    else:

        print(f"[PRODUCT ALREADY KNOWN] {brand} {model}")

    spec_json = json.dumps(claims)

    crawl_ts = utcnow_iso()

    conn.execute(
        """
        INSERT OR IGNORE INTO raw_specs (
            url,
            domain,
            crawl_ts,
            product_model,
            product_brand,
            product_title,
            spec_json,
            html_sha256,
            html_path,
            crawl_timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            url,
            domain,
            crawl_ts,
            model,
            brand,
            title,
            spec_json,
            html_sha,
            html_path,
            int(time.time())
        )
    )

    print(f"[RAW_SPECS INSERTED] {brand} {model} | {len(claims)} specs")


def snapshot_path(domain: str, sha256: str) -> str:
    return os.path.join(SNAPSHOT_DIR, domain, f"{sha256}.html.gz")


def store_page(conn, url, domain, status_code, sha256, path, crawl_ts):
    conn.execute(
        """
        INSERT OR IGNORE INTO crawl_pages
        (url, domain, crawl_ts, status_code, html_sha256, html_path)
        VALUES(?,?,?,?,?,?)
        """,
        (url, domain, crawl_ts, status_code, sha256, path),
    )


def url_already_crawled(conn, url: str):
    row = conn.execute(
        "SELECT 1 FROM crawl_pages WHERE url = ? LIMIT 1",
        (url,)
    ).fetchone()
    return row is not None


def html_already_seen(conn, sha: str):
    row = conn.execute(
        "SELECT 1 FROM crawl_pages WHERE html_sha256 = ? LIMIT 1",
        (sha,)
    ).fetchone()
    return row is not None


MODEL_REGEX = re.compile(r"\b[A-Z]{1,5}[A-Z0-9\-]*\d+[A-Z0-9\-]*\b")

def url_tokens(url: str):
    parsed = urlparse(url)
    path = parsed.path.lower()
    return set(re.findall(r"[a-z0-9_]+", path))


SPEC_HINT_TOKENS = {
    "spec",
    "specs",
    "specification",
    "specifications",
    "product",
    "products",
    "detail",
    "details",
    "attribute",
    "attributes",
    "techspec",
    "technical"
}


NOISE_ZONE_TOKENS = {
    "review",
    "reviews",
    "recommendation",
    "recommendations",
    "nav",
    "navigation",
    "footer",
    "ads",
    "pixel",
    "analytics",
    "telemetry",
    "tracking"
}


def calculate_source_trust(url: str):

    tokens = url_tokens(url)

    if tokens & NOISE_ZONE_TOKENS:
        return 0.0

    if tokens & SPEC_HINT_TOKENS:
        return 1.0

    return 0.5

def valid_model(model: str):

    if not model:
        return False

    model = model.strip().upper()

    if len(model) < 5:
        return False

    if not any(c.isdigit() for c in model):
        return False

    if not MODEL_REGEX.match(model):
        return False

    return True

def model_exists(conn, model):

    if not model:
        return False

    row = conn.execute(
        "SELECT 1 FROM crawl_products WHERE model = ? LIMIT 1",
        (model,)
    ).fetchone()

    return row is not None

def extract_links(html: str, base_url: str):

    links = set()
    base_domain = urlparse(base_url).netloc

    for match in re.findall(r'href=["\']([^"\']+)["\']', html):

        href = match.strip()

        if href.startswith("#"):
            continue
        if href.startswith("mailto:"):
            continue
        if href.startswith("tel:"):
            continue

        full = urljoin(base_url, href)
        parsed = urlparse(full)

        if parsed.netloc != base_domain:
            continue

        links.add(full)

    return links

def extract_jsonld_product(html):

    best = None
    best_score = -1

    try:

        scripts = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE
        )

        for s in scripts:

            try:
                data = json.loads(s)
            except:
                continue

            candidates = []

            if isinstance(data, dict):
                candidates.append(data)

            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        candidates.append(item)

            for obj in candidates:

                t = obj.get("@type")

                if isinstance(t, list):
                    is_product = "Product" in t or "ProductGroup" in t
                else:
                    is_product = t in ("Product", "ProductGroup")

                if not is_product:
                    continue

                mpn = obj.get("mpn")

                if not mpn:
                    mpn = obj.get("model")

                if not mpn:
                    mpn = obj.get("sku")

                if not mpn:
                    mpn = obj.get("productID")

                if not mpn:
                    title = obj.get("name", "")
                    m = MODEL_REGEX.search(title)
                    if m:
                        mpn = m.group(0)

                brand = None
                brand_obj = obj.get("brand")

                if isinstance(brand_obj, dict):
                    brand = brand_obj.get("name")

                elif isinstance(brand_obj, str):
                    brand = brand_obj

                score = 0

                if mpn:
                    score += 100

                if obj.get("additionalProperty"):
                    score += 50

                score += len(obj.keys())

                if score > best_score:

                    best_score = score

                    best = {
                        "identity": {
                            "brand": brand,
                            "model": mpn,
                            "title": obj.get("name")
                        },
                        "claims": []
                    }

    except:
        pass

    return best

def parse_sitemap(url):

    discovered = []

    try:
        r = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": USER_AGENT}
        )
        r.raise_for_status()
    except:
        return discovered

    try:
        root = ET.fromstring(r.text)
    except:
        return discovered

    for elem in root.iter():
        if "}" in elem.tag:
            elem.tag = elem.tag.split("}", 1)[1]

    sitemap_nodes = root.findall(".//sitemap")

    if sitemap_nodes:

        for node in sitemap_nodes:

            loc = node.find("loc")

            if loc is not None and loc.text:
                discovered.extend(parse_sitemap(loc.text.strip()))

        return discovered

    url_nodes = root.findall(".//url")

    for node in url_nodes:

        loc = node.find("loc")

        if loc is not None and loc.text:
            discovered.append(loc.text.strip())

    return discovered

def classify_source_type(html: str, brand: str | None = None, domain: str | None = None) -> str:

    print("\n[SLM SOURCE TYPE CLASSIFICATION]")

    text = extract_visible_text(html)
    text_sample = text[:4000]

    text = extract_visible_text(html)
    text_sample = text[:1000]

    current_brand = brand or "unknown"
    current_domain = domain or "unknown"

    brand_rule = f"If DOMAIN is NOT exactly the official site for {current_brand} (e.g. {current_brand.lower()}.com), it is NOT a manufacturer."

    print("\n----------- TEXT SENT TO SOURCE CLASSIFIER -----------")
    print(text_sample[:500])
    print("------------------------------------------------------")

    title = "unknown"

    prompt = f"""
You are classifying the SOURCE TYPE of a webpage based on STRUCTURE, not keywords.

KNOWN BRAND: {current_brand}
CURRENT DOMAIN: {current_domain}
PAGE TITLE: {title or "unknown"}

--------------------------------------------------
TASK
--------------------------------------------------

Choose EXACTLY one of the following:

manufacturer
retailer
review
spec_database
manual
government
blog
forum
unknown

--------------------------------------------------
CORE PRINCIPLE (VERY IMPORTANT)
--------------------------------------------------

Classify based on the OVERALL STRUCTURE and PURPOSE of the site.

Do NOT rely on individual words like:
"shop", "compare", "buy"

Instead determine:
- what kind of system this site is
- what role it plays (brand, marketplace, evaluator, etc.)

--------------------------------------------------
PRIMARY DISTINCTION (CRITICAL)
--------------------------------------------------

The key difference between manufacturer and retailer is BRAND SCOPE:

- manufacturer → represents ONE brand only
- retailer → sells products from MANY different brands

Transaction features (price, add to cart, checkout) can exist on BOTH
and do NOT determine the type by themselves.

--------------------------------------------------
DEFINITIONS
--------------------------------------------------

manufacturer:
Official website of a company that produces its own products.

Key signal:
The site focuses on a SINGLE brand.

It may include:
- product specs
- product pages
- pricing
- add to cart
- checkout

IMPORTANT:
Even if it includes purchasing features,
it is still a manufacturer if it ONLY sells its own brand.

Examples:
samsung.com
sony.com
apple.com
lg.com
bosch-home.com
geappliances.com


retailer:
Online store selling products from MANY different brands.

Key signal:
The site aggregates multiple brands.

Strong indicators:
- multiple brands shown together
- marketplace-style listings
- product comparisons across brands

Examples:
amazon.com
bestbuy.com
walmart.com
target.com
bhphotovideo.com
costco.com


review:
Evaluates products using ratings, scores, or testing.

Strong signals:
- numerical scores (e.g. 8/10, 87)
- reliability or satisfaction metrics
- lab testing descriptions
- comparisons between products
- editorial explanations

IMPORTANT:
Review sites DO NOT provide a true checkout flow.

Examples:
rtings.com
techradar.com
theverge.com
tomsguide.com
cnet.com
digitaltrends.com
consumerreports.org
wirecutter.com


spec_database:
Structured listings of product specifications across many products
with minimal editorial content.

Examples:
gsmarena.com
displayspecifications.com
notebookcheck.net
productz.com


manual:
Documentation or manuals.

Examples:
PDF manuals
support documentation
user guides
installation guides


government:
Official government or certification websites.

Examples:
energystar.gov
fcc.gov
epa.gov


blog:
Personal blog or informal article.


forum:
Community discussion or Q&A thread.

Examples:
reddit.com
stackexchange.com
forums.tomshardware.com


unknown:
If none of the above match.


--------------------------------------------------
CRITICAL RULES
--------------------------------------------------

1. STRUCTURE OVER KEYWORDS

Words like "shop", "compare", or product names
DO NOT determine the classification.

2. REVIEW OVERRIDE

If the page contains:
- ratings
- scores
- reliability metrics
- lab testing descriptions

Then it MUST be classified as "review",
even if products are shown.

3. RETAILER REQUIREMENT

A site is ONLY a retailer if:
- it aggregates MANY brands
AND
- functions as a marketplace or distributor

4. MANUFACTURER RULE

If the site represents a SINGLE brand,
it is a manufacturer, even if it sells products directly.

--------------------------------------------------
FEW-SHOT EXAMPLES
--------------------------------------------------

Example 1

Domain: samsung.com  
Text snippet:
"30 inch Induction Cooktop with Sync Burners. Model CC70F30S2DAA. Add to cart."

Output:
{{"source_type":"manufacturer"}}


Example 2

Domain: amazon.com  
Text snippet:
"Apple iPhone 15 Pro Max 256GB - Add to Cart. Sold by Amazon."

Output:
{{"source_type":"retailer"}}


Example 3

Domain: rtings.com  
Text snippet:
"The Samsung DU8000 has a native refresh rate of 60Hz and decent contrast."

Output:
{{"source_type":"review"}}


Example 4

Domain: gsmarena.com  
Text snippet:
"Samsung Galaxy S24 specs: 6.2-inch display, 50 MP camera, 4000 mAh battery."

Output:
{{"source_type":"spec_database"}}


Example 5

Domain: energystar.gov  
Text snippet:
"ENERGY STAR certified televisions meet strict efficiency guidelines."

Output:
{{"source_type":"government"}}


Example 6

Domain: consumerreports.org  
Text snippet:
"Overall Score, Predicted Reliability, Owner Satisfaction. Lab test results and product comparisons."

Output:
{{"source_type":"review"}}


--------------------------------------------------

Return ONLY JSON:

{{
  "source_type": "manufacturer|retailer|review|spec_database|manual|government|blog|forum|unknown"
}}

PAGE TEXT:
{text_sample[:1000]}
"""

    response = run_llm(prompt)
    data = safe_json_parse(response)

    if not data:
        return "unknown"

    source_type = data.get("source_type", "unknown")

    allowed = {
        "manufacturer",
        "retailer",
        "review",
        "spec_database",
        "manual",
        "government",
        "blog",
        "forum",
        "unknown",
    }

    if source_type not in allowed:
        return "unknown"

    print("[SOURCE TYPE]", source_type)

    return source_type


def discover_api_request(request):

    try:

        method = request.method
        url = request.url

        if method not in ["POST", "GET"]:
            return

        payload = request.post_data

        if payload is None:
            payload = ""

        if len(payload) < 5000:

            text = payload.lower()

            if any(k in text for k in [
                "sku",
                "product",
                "model",
                "spec",
                "details"
            ]):

                print("\n[API REQUEST DISCOVERED]")
                print("URL:", url)
                print("METHOD:", method)
                print("PAYLOAD:", payload)

    except:
        pass

def detect_spec_shape(obj):

    if not isinstance(obj, list):
        return False

    if len(obj) < 4:
        return False

    kv_like = 0

    for item in obj:

        if not isinstance(item, dict):
            continue

        keys = list(item.keys())

        if len(keys) == 2:

            values = list(item.values())

            if all(isinstance(v, (str, int, float)) for v in values):
                kv_like += 1

    return kv_like / len(obj) >= 0.8

def find_spec_structures(obj, results):

    if isinstance(obj, dict):

        for v in obj.values():
            find_spec_structures(v, results)

    elif isinstance(obj, list):

        if detect_spec_shape(obj):
            results.append(obj)

        for item in obj:
            find_spec_structures(item, results)

def detect_block_state(html: str, status_code=None, spec_rows=0, identity=None):
    identity = identity or {}
    lowered = html.lower() if html else ""

    if status_code in {401, 403, 429}:
        return True, f"http_{status_code}"

    negative_terms = [
        "access denied",
        "forbidden",
        "security check",
        "verify you are human",
        "verify you are not a bot",
        "captcha",
        "challenge",
        "just a moment",
        "temporarily blocked",
        "request blocked",
        "bot detection",
    ]

    negative_hits = sum(1 for term in negative_terms if term in lowered)

    has_identity = bool(identity.get("brand") or identity.get("model"))

    has_product_signals = any(term in lowered for term in [
        "spec",
        "specification",
        "features",
        "dimensions",
        "warranty",
        "model",
        "sku",
        "upc",
    ])

    html_len = len(html or "")

    if negative_hits >= 2 and not has_product_signals:
        return True, "challenge_text"

    if html_len < 15000 and spec_rows == 0 and not has_identity:
        return True, "low_entropy_no_identity"

    if html_len < 8000 and spec_rows == 0:
        return True, "tiny_page_no_specs"

    return False, None

def render_with_playwright(url, context):

    rendered_html = None
    extracted_specs = []
    specs_html = None
    api_specs = []

    blocked = False
    block_status = None
    block_url = None
    block_reason = None
    document_status = None

    try:

        print("[PLAYWRIGHT] opening:", url)

        page = context.new_page()

        page.set_viewport_size({"width": 1920, "height": 1080})

        page.on("console", lambda msg: print("[BROWSER CONSOLE]", msg.type, msg.text))
        page.on("pageerror", lambda err: print("[PAGE ERROR]", err))

        def detect_block_response(response):
            nonlocal blocked, block_status, block_url, document_status

            try:
                if response.request.resource_type == "document":
                    document_status = response.status

                    if response.status in {401, 403, 429}:
                        blocked = True
                        block_status = response.status
                        block_url = response.url

                        print(f"\n[{response.status} DOCUMENT BLOCK]")
                        print("URL:", response.url)
            except:
                pass

        def discover_api_response(response):

            try:

                if response.status == 403:
                    print("\n[403 RESPONSE DETECTED]")
                    print("URL:", response.url)
                    print("RESOURCE TYPE:", response.request.resource_type)
                    print("METHOD:", response.request.method)

                ct = response.headers.get("content-type", "")

                trust = calculate_source_trust(response.url)

                if trust == 0:
                    print("[DROPPED BY SOURCE]", response.url)
                    return

                if "json" not in ct.lower():
                    return

                try:
                    data = response.json()
                except:
                    return

                try:

                    if current_model:

                        json_text = json.dumps(data).upper()

                        if current_model.upper() in json_text:

                            print("\n[MODEL FOUND IN JSON RESPONSE]")
                            print("URL:", response.url)

                            json_blob = json.dumps(data)

                            api_specs.append({
                                "attribute": "json_capture",
                                "value": json_blob[:2000],
                                "unit": None,
                                "source_url": response.url,
                                "source_trust": trust
                            })

                except:
                    pass

                spec_structures = []

                find_spec_structures(data, spec_structures)

                if spec_structures:

                    print("\n[STRUCTURAL SPEC JSON DETECTED]")
                    print("URL:", response.url)

                    for structure in spec_structures:

                        for row in structure:

                            try:

                                keys = list(row.keys())

                                name = str(row[keys[0]]).strip()
                                value = str(row[keys[1]]).strip()

                                if not name or not value:
                                    continue

                                print(f"[API SPEC] {name} = {value}")

                                api_specs.append({
                                    "attribute": name,
                                    "value": value,
                                    "unit": None,
                                    "source_url": response.url,
                                    "source_trust": trust
                                })

                            except:
                                pass

            except:
                pass

        page.on("request", discover_api_request)
        page.on("response", discover_api_response)
        page.on("response", detect_block_response)

        response = page.goto(url, timeout=60000, wait_until="domcontentloaded")

        if response:
            document_status = response.status

            if response.status in {401, 403, 429}:
                blocked = True
                block_status = response.status
                block_url = url

        print("[PLAYWRIGHT] page loaded")

        human_delay(page, 2000, 5000)

        page.mouse.move(random.randint(100, 800), random.randint(100, 600))
        human_delay(page, 500, 1500)

        for _ in range(random.randint(2, 4)):
            page.mouse.wheel(0, random.randint(300, 900))
            human_delay(page, 800, 2000)

        try:

            buttons = page.query_selector_all("button")

            clicked = False

            for b in buttons:

                if clicked:
                    break

                try:
                    text = b.inner_text().lower()
                except:
                    continue

                if "specifications" in text or "specs" in text:
                    try:
                        print("[CLICKING SPEC BUTTON]")
                        b.click()
                        clicked = True
                        human_delay(page, 1000, 3000)
                    except:
                        pass

        except:
            pass

        page.screenshot(path="debug.png", full_page=True)

        rendered_html = page.content()

        rows = page.query_selector_all(
            "table tr, dl dt, dl dd, li[class*='spec'], div[class*='spec'], div[class*='Spec'], div[class*='feature'], div[class*='attribute']"
        )

        spec_row_count = len(rows)
        print("[PLAYWRIGHT] spec rows:", spec_row_count)

        semantic_blocked, semantic_reason = detect_block_state(
            html=rendered_html,
            status_code=document_status,
            spec_rows=spec_row_count,
            identity={"brand": None, "model": None}
        )

        if semantic_blocked and not blocked:
            blocked = True
            block_reason = semantic_reason
            block_status = document_status
            block_url = url
            print(f"[BLOCK DETECTED] {semantic_reason}")

        for r in rows:

            try:

                text = r.inner_text().strip()

                if not text:
                    continue

                if ":" in text:
                    name, value = text.split(":", 1)
                else:
                    parts = text.split("\n")

                    if len(parts) < 2:
                        continue

                    name = parts[0]
                    value = " ".join(parts[1:])

                name = name.strip()
                value = value.strip()

                if not name or not value:
                    continue

                print(f"[SPEC] {name} = {value}")

                extracted_specs.append({
                    "attribute": name,
                    "value": value,
                    "unit": None
                })

            except:
                pass

        seen_specs = set()
        deduped_specs = []

        for spec in extracted_specs:
            key = (
                spec.get("attribute", "").strip().lower(),
                str(spec.get("value", "")).strip().lower()
            )
            if key in seen_specs:
                continue
            seen_specs.add(key)
            deduped_specs.append(spec)

        extracted_specs = deduped_specs

        if api_specs:

            print(f"[API SPECS CAPTURED] {len(api_specs)}")

            for spec in api_specs:
                extracted_specs.append(spec)

        page.close()

    except Exception as e:
        print("[PLAYWRIGHT ERROR]", e)

    return rendered_html, specs_html, extracted_specs, api_specs, blocked, block_status, block_url, block_reason, document_status

def trigger_normalization_pipeline(model_id):
    def run():
        try:
            print(f"\n[POST-PROCESSING START] {model_id}")

            results = analyze_product(model_id)

            for r in results[:10]:
                print(r)

            print(f"[POST-PROCESSING DONE] {model_id}\n")

        except Exception as e:
            print("[POST-PROCESSING ERROR]", e)

    Thread(target=run).start()

def main():

    print(f"[DB PATH] {DB_PATH}")

    initialize_database(DB_PATH)
    conn = get_db(DB_PATH)

    playwright = sync_playwright().start()

    browser = playwright.chromium.connect_over_cdp("http://localhost:9222")

    context = browser.contexts[0]

    reset_frontier_pending()

    crawl_queue = deque()
    discovered_urls = set()

    print("\n[DISCOVERY MODE]", DISCOVERY_MODE)

    if DISCOVERY_MODE in ("sitemap", "hybrid"):

        print("\n[DISCOVERING SITEMAPS]\n")

        for sitemap_url in SITEMAP_URLS:

            print(f"[SITEMAP] {sitemap_url}")

            urls = parse_sitemap(sitemap_url)
            random.shuffle(urls)

            print(f"[SITEMAP URLS FOUND] {len(urls)}")

            for u in urls:
                if u not in discovered_urls:
                    discovered_urls.add(u)
                    crawl_queue.append(u)

    if DISCOVERY_MODE in ("sitemap", "hybrid"):

        for seed in SEED_URLS:
            crawl_queue.append(seed)

    print(f"\n[INITIAL URLS] {len(crawl_queue)}")

    crawled_count = 0

    while crawled_count < DEV_CRAWL_LIMIT:

        if not crawl_queue:

            frontier_url = get_next_frontier_url()

            if frontier_url:
                print(f"[FRONTIER] {frontier_url}")
                crawl_queue.append(frontier_url)
            else:
                break

        url = crawl_queue.popleft()

        global current_model
        current_model = None

        row = conn.execute(
            "SELECT 1 FROM raw_specs WHERE url = ? LIMIT 1",
            (url,)
        ).fetchone()

        if row:
            print("[SPECS ALREADY EXTRACTED — SKIPPING]", url)
            mark_frontier_complete(url)
            conn.commit()
            continue

        if DISCOVERY_MODE != "frontier":
            if url_already_crawled(conn, url):
                continue

        domain = get_domain(url)
        rate_limit(domain)

        print(f"[CRAWLING] {url}")

        if url.lower().endswith(".pdf"):
            print("[PDF DETECTED — SKIPPING PAGE]")
            mark_frontier_complete(url)
            conn.commit()
            continue

        domain = get_domain(url)

        crawl_ts = utcnow_iso()

        try:

            rendered_html, specs_html, extracted_specs, api_specs, blocked, block_status, block_url, block_reason, document_status = render_with_playwright(url, context)

            if not rendered_html:
                raise Exception("Playwright returned empty HTML")

            html = rendered_html

            if blocked:
                print(f"[BLOCKED PAGE] {url}")
                print("block_status:", block_status)
                print("block_url:", block_url)
                print("block_reason:", block_reason)

                count = retry_counts.get(url, 0) + 1
                retry_counts[url] = count

                if count >= MAX_RETRIES:
                    print("[FAILED — BLOCKED TOO MANY TIMES]")
                    mark_frontier_failed(url)
                else:
                    reset_frontier_pending()

                conn.commit()
                continue

            if "ERR_HTTP" in html or "This site can’t be reached" in html:
                print("[INVALID PAGE CONTENT]")
                reset_frontier_pending()
                conn.commit()
                continue

            sha = hashlib.sha256(html.encode("utf-8")).hexdigest()

            class FetchResult:
                pass

            fr = FetchResult()
            fr.html = html
            fr.sha256 = sha
            fr.status_code = document_status or 200

        except Exception as e:

            print("[RENDER FAILED]", url)

            count = retry_counts.get(url, 0) + 1
            retry_counts[url] = count

            if count >= MAX_RETRIES:
                print("[FAILED — RENDER ERROR]")
                mark_frontier_failed(url)
            else:
                reset_frontier_pending()
            conn.commit()
            continue

        if html_already_seen(conn, fr.sha256):
            print("[DUPLICATE HTML — SKIP STORAGE]")
            html_path = snapshot_path(domain, fr.sha256)

        else:
            html_path = snapshot_path(domain, fr.sha256)
            save_gz_text(fr.html, html_path)
            store_page(conn, url, domain, fr.status_code, fr.sha256, html_path, crawl_ts)

        crawled_count += 1

        html = fr.html

        if "Application error: a client-side exception has occurred" in html:

            with open("debug_samsung.html", "w", encoding="utf-8") as f:
                f.write(html)

            row = conn.execute(
                "SELECT attempts FROM crawl_frontier WHERE url = ?",
                (url,)
            ).fetchone()

            count = (row[0] if row else 0) + 1

            conn.execute(
                "UPDATE crawl_frontier SET attempts = ?, last_attempt_ts = ? WHERE url = ?",
                (count, utcnow_iso(), url)
            )
            retry_counts[url] = count

            print(f"[REACT ERROR PAGE — RETRY {count}/{MAX_RETRIES}]")

            if count >= MAX_RETRIES:
                print("[FAILED — MAX RETRIES]")
                mark_frontier_failed(url)
            else:
                reset_frontier_pending()

            conn.commit()
            continue

        # --------------------------------------------------
        # LAYER 1 — JSON-LD PRODUCT METADATA
        # --------------------------------------------------

        identity = {"brand": None, "model": None, "title": None}

        jsonld_data = extract_jsonld_product(html)

        if jsonld_data:

            print("[JSON-LD PRODUCT FOUND]")

            identity = jsonld_data.get("identity", {})

            current_model = identity.get("model")

            model = identity.get("model")

            if valid_model(model) and not model_exists(conn, model):

                conn.execute(
                    """
                    INSERT INTO crawl_products (model, brand, title)
                    VALUES (?, ?, ?)
                    """,
                    (
                        identity.get("model"),
                        identity.get("brand"),
                        identity.get("title")
                    )
                )

        print(f"[IDENTITY STORED] {identity.get('brand')} {identity.get('model')}")

        source_type = classify_source_type(
            html,
            brand=identity.get("brand"),
            domain=domain
        )

        prior = PRIORS_BY_TYPE.get(source_type, 1.0)
        upsert_source(conn, domain, source_type, prior)

        print("[ATTEMPTING EXTRACTION]")

        render_path = html_path.replace(".html.gz", "_rendered.html.gz")

        if rendered_html:
            save_gz_text(rendered_html, render_path)

            parsed = parse_page(
                html,
                url=url,
                rendered_specs=extracted_specs,
                source_type=source_type,
                api_specs=api_specs,
                conn=conn
            )

            claims = parsed.get("claims", []) if parsed else []

            print("\n[EXTRACTED SPECS]")
            for c in claims:
                print(f"{c.get('attribute')} = {c.get('value')} {c.get('unit')}")
            print()

            if claims:

                insert_raw_specs(
                    conn,
                    url,
                    domain,
                    fr.sha256,
                    render_path,
                    parsed
                )

                model = parsed.get("identity", {}).get("model")
                if model:
                    trigger_normalization_pipeline(model)

                context.storage_state(path="state.json")

                mark_frontier_complete(url)

            else:

                print("[FAILED — NO VALID SPECS]")
                mark_frontier_failed(url)

            print("\n[PARSED PRODUCT DATA]")
            print(parsed)
            print()

            conn.commit()

    context.close()
    playwright.stop()

    print("\n[CRAWL COMPLETE]")


if __name__ == "__main__":
    main()