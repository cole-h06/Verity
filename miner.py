import asyncio
import random
import re
import json
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig
from brain import process_product, PILLARS
from db import get_db, insert_claim, mark_complete, mark_failed, mark_unresolved, upsert_product, upsert_price, log_crawl
from search_bridge import run_search_bridge
from config import HIGH_SECURITY_DOMAINS, HEAVY_JS_DOMAINS, INTERACTIVE_DOMAINS, IDENTITY_RESET_MODE, REBUILD_MODE
from scout import fetch_with_retry
from openai import OpenAI


client = OpenAI()


def extract_product_nodes(json_ld):
    results = []

    def walk(obj):
        if isinstance(obj, dict):
            t = obj.get("@type")

            if t == "Product" or (isinstance(t, list) and "Product" in t):
                results.append(obj)

            for v in obj.values():
                walk(v)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(json_ld)
    return results


def normalize_gtin(gtin):
    if not gtin:
        return None
    gtin = re.sub(r"\D", "", str(gtin))
    if len(gtin) == 13 and gtin.startswith("0"):
        return gtin[1:]
    return gtin if len(gtin) in (12, 13, 14) else None


def gtin_similarity(a, b):
    a = normalize_gtin(a)
    b = normalize_gtin(b)

    if not a or not b:
        return 0.0

    if a == b:
        return 1.0

    if a.lstrip("0") == b.lstrip("0"):
        return 0.99

    matches = 0

    for x, y in zip(a, b):
        if x == y:
            matches += 1

    score = matches / max(len(a), len(b))

    if len(a) > 4 and len(b) > 4:
        if a[:4] != b[:4]:
            score *= 0.5

    return score


def extract_model_from_text(markdown, html):
    text = f"{markdown or ''}\n{html or ''}"

    patterns = [
        r"(?:Model\s*(?:Number|No\.?|#)?|MPN)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-\/\.]{4,})",
        r'"(?:model|model_number|mpn)"\s*:\s*"([^"]+)"'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue

        candidate = match.group(1).strip().upper()

        if is_valid_model(candidate):
            print(f"[MODEL TEXT FOUND] {candidate}")
            return candidate

        print(f"[MODEL TEXT REJECTED] {candidate}")

    return None


def extract_sku_from_text(markdown, html):
    text = f"{markdown or ''}\n{html or ''}"

    match = re.search(
        r"(?:SKU)\s*[:#]?\s*(\d{5,})",
        text,
        re.IGNORECASE
    )

    if match:
        return match.group(1).strip()

    return None


def count_claims(conn, product_id):
    if not product_id:
        return 0

    row = conn.execute(
        "SELECT COUNT(*) as c FROM raw_claims WHERE product_id=?",
        (product_id,)
    ).fetchone()

    return row["c"] if row else 0


def clean_price(p):
    if not p:
        return None
    p = str(p)
    p = re.sub(r"[^\d.]", "", p)
    try:
        return float(p)
    except Exception:
        return None


def extract_json_ld_from_html(html):
    matches = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or "",
        re.DOTALL | re.IGNORECASE
    )

    for match in matches:
        try:
            parsed = json.loads(match.strip())
        except Exception:
            continue

        products = extract_product_nodes(parsed)
        if products:
            return parsed

    return {}


def extract_json_ld_claims(product):
    claims = []

    if not product:
        return claims

    name = product.get("name")
    if name:
        claims.append(("product_name", name))

    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    if brand:
        claims.append(("brand", brand))

    model = product.get("model") or product.get("mpn")
    if model:
        claims.append(("model", model))

    sku = product.get("sku")
    if sku:
        claims.append(("sku", sku))

    color = product.get("color")
    if color:
        claims.append(("color", color))

    for prop in product.get("additionalProperty", []):
        if not isinstance(prop, dict):
            continue
        prop_name = prop.get("name")
        prop_value = prop.get("value")
        if prop_name and prop_value:
            claims.append((prop_name, prop_value))

    return claims


def dedupe_claims(claims):
    seen = set()
    deduped = []

    for attr, value in claims:
        if not attr or value is None:
            continue

        key = (
            str(attr).strip().lower(),
            str(value).strip().lower()
        )

        if key in seen:
            continue

        seen.add(key)
        deduped.append((attr, value))

    return deduped


def get_pillar_count(structured, category):
    pillar_keys = PILLARS.get(category, [])
    return sum(1 for k, _ in structured if k in pillar_keys)


def normalize_domain(url: str) -> str:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    parts = domain.split(".")
    if len(parts) >= 2:
        domain = ".".join(parts[-2:])
    return domain


def get_source_type(conn, url):
    domain = normalize_domain(url)

    row = conn.execute(
        "SELECT source_type FROM sources WHERE domain=?",
        (domain,)
    ).fetchone()

    if row:
        return row["source_type"]

    return "unknown"


def is_valid_spec_table(rows):

    if not rows:
        return False

    keys = [
        str(k).lower().strip()
        for k, _ in rows
    ]

    unique_keys = len(set(keys))

    repeated_ratio = 1 - (
        unique_keys / max(len(keys), 1)
    )

    if repeated_ratio > 0.6:
        return False

    return True


def extract_generic_html_specs(html):
    generic_specs = []

    if not html:
        return generic_specs

    soup = BeautifulSoup(html, "lxml")

    tables = soup.find_all("table")

    for table in tables:

        table_specs = []

        rows = table.find_all("tr")

        for row in rows:

            th = row.find("th")
            td = row.find("td")

            if th and td:

                label = th.get_text(" ", strip=True)
                value = td.get_text(" ", strip=True)

                if not label or not value:
                    continue

                if len(label) > 200 or len(value) > 500:
                    continue

                table_specs.append((label, value))
                continue

            cols = [
                c.get_text(" ", strip=True)
                for c in row.find_all(["td", "th"])
            ]

            cols = [c for c in cols if c]

            if len(cols) < 2:
                continue

            if len(cols) % 2 != 0:
                continue

            for i in range(0, len(cols) - 1, 2):

                label = cols[i]
                value = cols[i + 1]

                if not label or not value:
                    continue

                if len(label) > 200 or len(value) > 500:
                    continue

                table_specs.append((label, value))

        if is_valid_spec_table(table_specs):
            generic_specs.extend(table_specs)

    cards = soup.select(
        ".full-specifications__specifications-single-card"
    )

    for card in cards:

        rows = card.select(
            ".full-specifications__specifications-single-card__sub-list"
        )

        for row in rows:

            name_el = row.select_one(
                ".full-specifications__specifications-single-card__sub-list__name"
            )

            value_el = row.select_one(
                ".full-specifications__specifications-single-card__sub-list__value"
            )

            if not name_el or not value_el:
                continue

            label = name_el.get_text(" ", strip=True)
            value = value_el.get_text(" ", strip=True)

            if not label or not value:
                continue

            generic_specs.append((label, value))

    return dedupe_claims(generic_specs)


def clean_html(text):
    if not text:
        return ""

    clean = re.sub(r"<.*?>", "", text)

    if ":" in clean:
        parts = clean.split(":", 1)
        if len(parts[0]) < 40:
            clean = parts[1]

    return clean.strip()


def extract_hard_ids(raw_text):
    identities = []

    try:
        raw_text = raw_text or ""

        match = re.search(r'"(?:primary_barcode|gtin12|gtin13|upc)"\s*:\s*"(\d{12,13})"', raw_text)
        if match:
            identities.append(("gtin", match.group(1)))
        else:
            match = re.search(r'\b((?:0|1|6|7|8)\d{11})\b', raw_text)
            if match:
                identities.append(("gtin", match.group(1)))

        dpci_match = re.search(r'\b(\d{3}-\d{2}-\d{4})\b', raw_text)
        if dpci_match:
            identities.append(("dpci", dpci_match.group(1)))

        model_match = re.search(r'"model_number"\s*:\s*"([^"]+)"', raw_text)
        if not model_match:
            model_match = re.search(r'"(?:model|mpn)"\s*:\s*"([^"]+)"', raw_text)

        if model_match:
            identities.append(("model", model_match.group(1)))

        return list(set(identities))

    except Exception as e:
        print(f"[ID EXTRACTION ERROR]: {e}")
        return []


def extract_labeled_ids(markdown):
    identity = {"gtin": None, "model": None}

    patterns = [
        (r"(?:UPC|GTIN|EAN)[^:\n]*[:\-]\s*(\d{12,14})", "gtin"),
        (r"(?:Model(?:\s*Number)?|MPN)[^:\n]*[:\-]\s*([A-Z0-9\-]{4,})", "model"),
    ]

    for pattern, key in patterns:
        match = re.search(pattern, markdown or "", re.IGNORECASE)
        if match:
            val = match.group(1).strip()

            if key == "gtin" and val.isdigit():
                identity["gtin"] = val

            elif key == "model":
                val = val.upper()
                if re.search(r"[A-Z]", val) and re.search(r"\d", val):
                    identity["model"] = val

    return identity


def extract_model_fallback(markdown):
    if not markdown:
        return None

    match = re.search(r"-\s*([A-Z0-9\-]{5,})", markdown)
    if match:
        return match.group(1).upper()

    match = re.search(r"\b([A-Z]{2,}-?[A-Z0-9]{3,})\b", markdown)
    if match:
        return match.group(1).upper()

    return None


def is_valid_model(model):
    if not model:
        return False

    m = str(model).strip().upper()

    if len(m) < 5 or len(m) > 40:
        return False

    if not (re.search(r"[A-Z]", m) and re.search(r"\d", m)):
        return False

    if not re.search(r"[A-Z]+\d+|\d+[A-Z]+", m):
        return False

    if re.fullmatch(r"\d+(\.\d+)?\s?(GB|TB|MB|KB|GHZ|MHZ|HZ|W|WH|MAH|AH|IN|CM|MM|LB|LBS|KG|G|OZ|QT|V|A)", m):
        return False

    if re.fullmatch(r"\d+(\.\d+)?", m):
        return False

    parts = re.split(r"[-_/.\s]+", m)
    if all(re.fullmatch(r"[A-Z]+", p) for p in parts if p):
        return False

    return True


def normalize_model_tokens(model):
    if not model:
        return []

    model = model.upper()
    return re.findall(r"[A-Z]+|\d+", model)


def model_similarity(a, b):
    if not a or not b:
        return 0.0

    a = a.upper()
    b = b.upper()

    if a == b:
        return 1.0

    a_tokens = normalize_model_tokens(a)
    b_tokens = normalize_model_tokens(b)

    a_digits = "".join(t for t in a_tokens if t.isdigit())
    b_digits = "".join(t for t in b_tokens if t.isdigit())

    if not a_digits or not b_digits or a_digits != b_digits:
        return 0.0

    a_alpha = "".join(t for t in a_tokens if t.isalpha())
    b_alpha = "".join(t for t in b_tokens if t.isalpha())

    score = 0.0

    if a_digits and b_digits and a_digits == b_digits:
        score += 0.45

    if a_alpha and b_alpha and (a_alpha in b_alpha or b_alpha in a_alpha):
        score += 0.30

    if a in b or b in a:
        score += 0.20

    overlap = len(set(a_tokens) & set(b_tokens))
    total = max(len(set(a_tokens)), 1)
    score += 0.05 * (overlap / total)

    if score >= 0.5:
        print(f"[MODEL SIM] {a} <-> {b} = {score:.2f}")

    return min(score, 1.0)


def find_existing_by_model(conn, model, threshold=0.80):
    if not model:
        return None

    rows = conn.execute("""
        SELECT *
        FROM products
        WHERE model IS NOT NULL
    """).fetchall()

    best = None
    best_score = 0.0

    for row in rows:
        score = model_similarity(model, row["model"])

        if score > best_score:
            best_score = score
            best = row

    print(f"[MODEL SEARCH] input={model} best={best['model'] if best else None} score={best_score:.2f}")

    if best and best_score >= threshold:
        print(f"[FUZZY MODEL MATCH] {model} -> {best['model']} ({best_score:.2f})")
        return best

    return None


def has_model_support(markdown, model):
    if not model or not markdown:
        return False

    m = model.lower()
    text = markdown.lower()

    if text.count(m) >= 2:
        return True

    if re.search(rf"(model|mpn)[^a-z0-9]{{0,10}}{re.escape(m)}", text):
        return True

    return False


def find_specs(obj):
    results = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            key = k.lower()

            if key == "bundlespecificationdetails" and isinstance(v, list):
                results.extend(v)

            elif key == "specificationgroup" and isinstance(v, list):
                for group in v:
                    if isinstance(group, dict):
                        specs = group.get("specifications", [])
                        if isinstance(specs, list):
                            results.extend(specs)

            else:
                results.extend(find_specs(v))

    elif isinstance(obj, list):
        for item in obj:
            results.extend(find_specs(item))

    return results


def extract_target_specs(data):
    results = []

    try:
        product = data.get("data", {}).get("product", {})
        item = product.get("item", {})
        description = item.get("product_description", {})

        specs = description.get("soft_specifications", {}).get("specifications", [])
        for s in specs:
            label = s.get("label")
            value = s.get("value")
            if label and value:
                results.append((clean_html(label), clean_html(value)))

        bullets = description.get("bullet_descriptions", [])
        for b in bullets:
            if b:
                raw = re.sub(r"<.*?>", "", b).strip()

                if ":" in raw:
                    name, value = raw.split(":", 1)
                    results.append((name.strip(), value.strip()))
                else:
                    clean = clean_html(b)
                    results.append(("feature", clean))

    except Exception as e:
        print(f"[TARGET PARSE ERROR]: {e}")

    if not results:
        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    key = k.lower()

                    if key in ["soft_specifications", "softspecifications", "bullet_description", "item_attributes", "specifications"]:
                        if isinstance(v, list):
                            for item in v:
                                if isinstance(item, str):
                                    results.append(("feature", clean_html(item)))
                                elif isinstance(item, dict):
                                    name = (
                                        item.get("label")
                                        or item.get("name")
                                        or item.get("specification_name")
                                    )
                                    value = (
                                        item.get("value")
                                        or item.get("definition")
                                        or item.get("specification_value")
                                    )
                                    if name and value:
                                        results.append((clean_html(name), clean_html(value)))

                    walk(v)

            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(data)

    return list(set(results))


def get_target_tcin(url):
    match = re.search(r"/A-(\d+)", url)
    return match.group(1) if match else None


def get_upc(html):
    try:
        match = re.search(r'"primary_barcode"\s*:\s*"(\d{12,13})"', html or "")

        if not match:
            match = re.search(r'"gtin(?:12|13|14)?"\s*:\s*"(\d{12,14})"', html or "")

        if not match:
            match = re.search(r'"upc"\s*:\s*"(\d{12,13})"', html or "")

        if match:
            upc = match.group(1)
            print(f"[HTML UPC FOUND]: {upc}")
            return upc

    except Exception as e:
        print(f"[HTML UPC ERROR]: {e}")

    return None


def get_target_specs_direct(url):
    tcin = get_target_tcin(url)
    if not tcin:
        print("[TARGET API ERROR]: Could not extract TCIN from URL")
        return []

    params = {
        "key": "9f36aeafbe60771e321a7cc95a78140772ab3e96",
        "tcin": tcin,
        "store_id": "3991",
        "pricing_store_id": "3991",
        "has_pricing_store_id": "true",
        "is_bot": "false"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.target.com/",
        "Origin": "https://www.target.com"
    }

    try:
        response = requests.get(
            "https://redsky.target.com/redsky_aggregations/v1/web/pdp_client_v1",
            params=params,
            headers=headers,
            timeout=20
        )

        data = response.json()

        product_data = data.get("data", {}).get("product", {})
        item = product_data.get("item", {})
        desc = item.get("product_description", {})
        price_info = product_data.get("price", {})

        title = desc.get("title")
        brand = (
            item.get("primary_brand", {}).get("name")
            or item.get("product_brand", {}).get("name")
        )
        price = price_info.get("current_retail")
        image = (
            item.get("enrichment", {}).get("images", {}).get("primary_image_url")
            or item.get("images", {}).get("primary_image_url")
        )
        model = desc.get("model_number")

        product_item = product_data.get("item", {})
        upc = product_item.get("primary_barcode")

        next_specs = extract_target_specs(data)

        if upc:
            upc = normalize_gtin(upc)
            print(f"[FOUND UPC]: {upc}")
            next_specs.append(("gtin", upc))

        if not upc:
            try:
                html_headers = {
                    "User-Agent": headers["User-Agent"],
                    "Accept": "text/html",
                    "Referer": "https://www.target.com/"
                }

                html_resp = requests.get(url, headers=html_headers, timeout=20)
                html_upc = get_upc(html_resp.text)

                if html_upc:
                    html_upc = normalize_gtin(html_upc)
                    print(f"[FOUND HTML UPC]: {html_upc}")
                    next_specs.append(("gtin", html_upc))

            except Exception as e:
                print(f"[TARGET HTML UPC ERROR]: {e}")

        if title:
            next_specs.append(("title", title))

        if brand:
            next_specs.append(("brand", brand))

        if price:
            next_specs.append(("price", price))

        if image:
            next_specs.append(("image_url", image))

        if model:
            next_specs.append(("model", model))

        return next_specs

    except Exception as e:
        print(f"[TARGET API ERROR]: {e}")
        return []


def extract_walmart_specs(data):
    results = []

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = k.lower()

                if key in ["specifications", "attributes", "allattributes", "idml"]:
                    if isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict):
                                name = (
                                    item.get("name")
                                    or item.get("specName")
                                    or item.get("attributeName")
                                )
                                value = (
                                    item.get("value")
                                    or item.get("specValue")
                                    or item.get("attributeValue")
                                )

                                if name and value:
                                    results.append((name, value))

                walk(v)

        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return list(set(results))

def run_llm_identity(markdown: str):
    if not markdown:
        return {}

    try:
        cleaned = markdown[:20000]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": """
Extract ONLY explicitly stated values from the text.

Return a JSON object with:
- gtin (12–14 digit number ONLY if directly present)
- model (must contain BOTH letters and numbers, ONLY if explicitly present)

STRICT RULES:
- Do NOT infer or guess
- Do NOT fabricate values
- Do NOT normalize or modify values
- Do NOT extract partial matches
- If not clearly written, do not return it
- If nothing is found, return {}

Output MUST be valid JSON.
"""
                },
                {"role": "user", "content": cleaned}
            ],
            temperature=0
        )

        data = json.loads(response.choices[0].message.content)

        gtin = data.get("gtin")
        model = data.get("model")

        if gtin:
            gtin = str(gtin).strip()
            if not (gtin.isdigit() and 12 <= len(gtin) <= 14):
                gtin = None

        if model:
            model = model.strip().upper()
            if not is_valid_model(model):
                model = None

        return {
            "gtin": gtin,
            "model": model
        }

    except Exception as e:
        print("[LLM ERROR]", e)
        return {}
        
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

    page_row = conn.execute("""
        SELECT id
        FROM crawled_pages
        WHERE url=?
        ORDER BY id DESC
        LIMIT 1
    """, (url,)).fetchone()

    page_id = page_row["id"] if page_row else None

    linked_product_id = None

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
            linked_product_id = linked_claim["product_id"]

    linked_product = None

    if linked_product_id:
        linked_product = conn.execute("""
            SELECT *
            FROM products
            WHERE
                gtin=?
                OR lower(model)=lower(?)
            LIMIT 1
        """, (
            linked_product_id,
            linked_product_id
        )).fetchone()

    existing_gtin = None
    existing_model = None

    if linked_product:
        existing_gtin = normalize_gtin(linked_product["gtin"])

        if is_valid_model(linked_product["model"]):
            existing_model = linked_product["model"]
 
    needs_identity_enrichment = not (
        existing_gtin or existing_model
    )

    existing_claim_count = count_claims(
        conn,
        linked_product_id
    )

    MIN_CLAIMS = 10

    needs_spec_rebuild = (
        existing_claim_count < MIN_CLAIMS
    )

    print("existing_claim_count:", existing_claim_count)
    print("needs_spec_rebuild:", needs_spec_rebuild)

    is_identity_mode = (
        IDENTITY_RESET_MODE
        and needs_identity_enrichment
    )

    print("\n=== IDENTITY CHECK ===")
    print("existing_gtin:", existing_gtin)
    print("existing_model:", existing_model)
    print("needs_identity_enrichment:", needs_identity_enrichment)
    should_recrawl = (
        needs_identity_enrichment
        or needs_spec_rebuild
    )

    print("\n=== RECRAWL CHECK ===")
    print("needs_identity_enrichment:", needs_identity_enrichment)
    print("needs_spec_rebuild:", needs_spec_rebuild)
    print("should_recrawl:", should_recrawl)
 
    is_rebuild_mode = (
        REBUILD_MODE and should_recrawl
    )

    if is_rebuild_mode:
        print("[MODE] REBUILD")
    elif is_identity_mode:
        print("[MODE] IDENTITY")
    else:
        print("[MODE] NORMAL")

    if status == "failed" and not is_rebuild_mode:
        print(f"[SKIP FAILED] {url}")
        conn.close()
        return {"skipped": True}

    if ".pdf" in url.lower():
        print(f"[SKIP PDF] {url}")
        mark_complete(conn, url)
        conn.commit()
        conn.close()
        return {"skipped": True}

    if existing_gtin or existing_model:
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
            resolved_gtin = normalize_gtin(resolved["gtin"])
            resolved_model = resolved["model"]

            print("[PRE-CRAWL RESOLVED]")
            print("GTIN:", resolved_gtin)
            print("MODEL:", resolved_model)

            print("[IDENTITY COMPLETE - SKIPPING RECRAWL]")
            if resolved_gtin and resolved_model and not should_recrawl:
                print("[SKIP FULL RECRAWL - SUFFICIENT DATA EXISTS]")

                mark_complete(conn, url)

                return {
                    "gtin": resolved_gtin,
                    "model": resolved_model,
                    "skipped": True
                }

    try:
        raw_domain = urlparse(url).netloc.lower()
        domain = normalize_domain(url)

        is_heavy_js = any(d in raw_domain for d in HEAVY_JS_DOMAINS)
        is_interactive = any(d in raw_domain for d in INTERACTIVE_DOMAINS)
        use_cdp = any(d in raw_domain for d in HIGH_SECURITY_DOMAINS)
        is_home_depot = "homedepot.com" in domain
        is_jbl = "jbl.com" in domain

        print(f"[ROUTING] {'CDP' if use_cdp else 'STANDARD'} -> {raw_domain}")

        browser_config = BrowserConfig(
            browser_type="chromium",
            headless=True
        )

        wait_for = """
        js:() => {
            const text = document.body.innerText.toLowerCase();
            const len = text.length;

            const hasSpecSignal =
                text.includes("processor") ||
                text.includes("memory") ||
                text.includes("storage") ||
                text.includes("display") ||
                text.includes("battery");

            if (!window.__peelr_state) {
                window.__peelr_state = {
                    base_len: len,
                    last_len: len,
                    stableCount: 0
                };
                return false;
            }

            if (len > window.__peelr_state.last_len + 1500) {
                window.__peelr_state.last_len = len;
                window.__peelr_state.stableCount = 0;
                return false;
            }

            window.__peelr_state.stableCount += 1;

            const grewEnough = len > window.__peelr_state.base_len + 1500;

            return (grewEnough && window.__peelr_state.stableCount >= 2) || hasSpecSignal;
        }
        """

        delay = 25.0 if is_heavy_js else 3.0
        remove_overlay = False if is_heavy_js else True

        HEAVY_JS_SCRIPT = """(async () => { await new Promise(r => setTimeout(r, 6000)); window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 4000)); })();"""

        DEFAULT_JS = """(async () => { await new Promise(r => setTimeout(r, 4000)); window.scrollTo(0, document.body.scrollHeight); await new Promise(r => setTimeout(r, 4000)); })();"""

        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            scan_full_page=True,
            flatten_shadow_dom=True,
            excluded_selector="header, footer, nav, aside",
            remove_overlay_elements=remove_overlay,
            process_iframes=True,
            wait_for=wait_for,
            wait_for_timeout=30000,
            delay_before_return_html=delay,
            js_code_before_wait=HEAVY_JS_SCRIPT if is_heavy_js else DEFAULT_JS,
            js_code=None
        )

        result = None
        html = ""
        markdown = ""
        spec_payloads = []
        next_specs = []
        generic_specs = []
        extracted_specs = []
        skip_generic_html = False

        if use_cdp:
            if is_home_depot:
                async with async_playwright() as p:
                    browser = await p.chromium.connect_over_cdp("http://localhost:9222")
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else await context.new_page()

                    async def handle_response(response):
                        try:
                            if "graphql" not in response.url:
                                return

                            print("\n[GRAPHQL URL]:", response.url)

                            data = await response.json()

                            if not isinstance(data, dict):
                                return

                            if "productClientOnlyProduct" in response.url:
                                spec_payloads.append(data)
                                print("[CAPTURED PRODUCT PAYLOAD]")
                        except:
                            pass

                    page.on("response", lambda response: asyncio.create_task(handle_response(response)))

                    await page.goto(url)
                    await page.wait_for_load_state("domcontentloaded")
                    try:
                        await page.wait_for_load_state("networkidle")
                    except:
                        pass
                    await page.wait_for_timeout(3000)

                    await page.wait_for_timeout(8000)
                    html = await page.content()

                soup = BeautifulSoup(html, "lxml")
                markdown = soup.get_text("\n", strip=True)

                result = type("obj", (), {"success": True, "status_code": 200, "url": url, "html": html, "markdown": None})()

            elif is_jbl:
                async with async_playwright() as p:
                    browser = await p.chromium.connect_over_cdp("http://localhost:9222")
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else await context.new_page()

                    jbl_payloads = []

                    async def handle_response(response):
                        try:
                            url = response.url.lower()

                            if any(k in url for k in ["product", "products", "dw", "api"]):
                                data = await response.json()

                                if isinstance(data, dict):
                                    jbl_payloads.append(data)
                                    print("[JBL PAYLOAD]", url)
                        except:
                            pass

                    page.on("response", lambda r: asyncio.create_task(handle_response(r)))

                    await page.goto(url)
                    await page.wait_for_load_state("domcontentloaded")

                    try:
                        await page.wait_for_load_state("networkidle")
                    except:
                        pass

                    await page.wait_for_timeout(5000)

                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")
                    markdown = soup.get_text("\n", strip=True)

                    for payload in jbl_payloads:
                        try:
                            specs = find_specs(payload)

                            for spec in specs:
                                name = (
                                    spec.get("specName")
                                    or spec.get("name")
                                    or spec.get("label")
                                )
                                value = (
                                    spec.get("specValue")
                                    or spec.get("value")
                                )

                                if name and value:
                                    next_specs.append((name, value))
                        except:
                            pass

                print("\n[JBL SPECS COUNT]:", len(next_specs))
                if next_specs:
                    print("[JBL SAMPLE]:", next_specs[:5])

                result = type("obj", (), {
                    "success": True,
                    "status_code": 200,
                    "url": url,
                    "html": html,
                    "markdown": None
                })()

            else:
                if "target.com" in domain:
                    print("\n[USING TARGET REDSKY API]")

                    next_specs = get_target_specs_direct(url)

                    print("\n[TARGET SPECS COUNT]:", len(next_specs))

                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html",
                        "Referer": "https://www.target.com/"
                    }

                    try:
                        html_resp = requests.get(url, headers=headers, timeout=20)
                        html = html_resp.text or ""
                    except Exception as e:
                        print(f"[TARGET HTML FETCH ERROR]: {e}")
                        html = ""
 
                    soup = BeautifulSoup(html, "lxml")
                    markdown = soup.get_text("\n", strip=True)

                    html_upc = get_upc(html)
                    if html_upc:
                        html_upc = normalize_gtin(html_upc)
                        if html_upc:
                            next_specs.append(("gtin", html_upc))
                            print(f"[TARGET HTML GTIN APPENDED]: {html_upc}")

                    result = type("obj", (), {
                        "success": True,
                        "status_code": 200,
                        "url": url,
                        "html": html,
                        "markdown": None
                    })()

                else:
                    async with async_playwright() as p:
                        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
                        context = browser.contexts[0]
                        page = context.pages[0] if context.pages else await context.new_page()

                        await page.goto(url)
                        await page.wait_for_load_state("domcontentloaded")

                        try:
                            await page.wait_for_load_state("networkidle")
                        except:
                            pass

                        if "target.com" in domain:
                            for _ in range(3):
                                await page.mouse.wheel(0, 2000)
                                await page.wait_for_timeout(1500)

                            try:
                                await page.wait_for_function(
                                    """
                                    () => {
                                        const scripts = Array.from(document.querySelectorAll("script"));
                                        return scripts.some(s => {
                                            const txt = s.innerText || "";
                                            return txt.includes("__TGT_DATA__") ||
                                                   txt.includes("softSpecifications") ||
                                                   txt.includes("soft_specifications") ||
                                                   txt.includes("bullet_description") ||
                                                   txt.includes("item_attributes");
                                        });
                                    }
                                    """,
                                    timeout=15000
                                )
                            except:
                                pass

                        else:
                            await page.wait_for_timeout(3000)
                            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            await page.wait_for_timeout(5000)

                        html = await page.content()

                    soup = BeautifulSoup(html, "lxml")

                    try:
                        if "target.com" in domain:
                            target_tag = None
                            all_scripts = soup.find_all("script")

                            for script in all_scripts:
                                content = script.string if script.string else ""

                                if "__TGT_DATA__" in content:
                                    if "getOwnPropertyNames" in content:
                                        continue

                                    if "window.__TGT_DATA__ =" in content or "self.__TGT_DATA__ =" in content:
                                        target_tag = script
                                        print("\n[SUCCESS] Found REAL Target data tag")
                                        break

                            if target_tag:
                                print("\n[TARGET DETECTED - CDP]")

                                raw = target_tag.string.strip()
                                data = None

                                start_idx = raw.find("{")
                                end_idx = raw.rfind("}")

                                if start_idx != -1 and end_idx != -1:
                                    json_str = raw[start_idx:end_idx + 1]

                                    try:
                                        data = json.loads(json_str)
                                    except Exception as e:
                                        print(f"[!] Failed to parse Target JSON: {e}")
                                        print("[DEBUG SAMPLE]:", json_str[:200])
                                        data = None
                                else:
                                    print("[!] Could not isolate JSON object")

                                if data:
                                    next_specs = extract_target_specs(data)

                                    print("\n[TARGET SPECS COUNT]:", len(next_specs))
                                    if next_specs:
                                        print("[SAMPLE]:", next_specs[:3])
                                else:
                                    print("\n[NO PARSEABLE TARGET DATA FOUND]")
                            else:
                                print("\n[NO TARGET DATA FOUND]")

                        elif "walmart.com" in domain:
                            next_data_tag = soup.find("script", id="__NEXT_DATA__")

                            if next_data_tag:
                                print("\n[WALMART DETECTED - CDP]")

                                data = json.loads(next_data_tag.string)
                                next_specs = extract_walmart_specs(data)

                                print("\n[WALMART SPECS COUNT]:", len(next_specs))
                                if next_specs:
                                    print("[SAMPLE]:", next_specs[:3])
                                else:
                                    print("[!] Walmart returned 0 specs")

                                if not next_specs:
                                    redux_tag = soup.find("script", id="__WML_REDUX_INITIAL_STATE__")

                                    if redux_tag:
                                        print("\n[FOUND REDUX STATE]")

                                        raw = redux_tag.string
                                        if raw.startswith("window.__WML_REDUX_INITIAL_STATE__"):
                                            raw = raw.split("=", 1)[1].strip().rstrip(";")

                                        data = json.loads(raw)
                                        next_specs = extract_walmart_specs(data)

                                        print("\n[REDUX RECURSIVE SPECS COUNT]:", len(next_specs))
                                        if next_specs:
                                            print("[REDUX SAMPLE]:", next_specs[:3])
                                        else:
                                            print("[!] Redux also returned 0.")

                    except:
                        pass

                    skip_generic_html = bool(next_specs or extracted_specs)

                    if skip_generic_html:
                        print("[STRUCTURED SPECS FOUND - SKIPPING GENERIC HTML]")

                    generic_specs = []

                    if not skip_generic_html:
                        generic_specs = extract_generic_html_specs(html)

                    print(f"[GENERIC HTML SPECS] {len(generic_specs)}")
                    print(generic_specs[:15])

                    markdown = soup.get_text("\n", strip=True)

                    result = type("obj", (), {"success": True, "status_code": 200, "url": url, "html": html, "markdown": None})()

        else:
            if "target.com" in domain:
                print("\n[USING TARGET REDSKY API]")

                next_specs = get_target_specs_direct(url)

                print("\n[TARGET SPECS COUNT]:", len(next_specs))

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html",
                    "Referer": "https://www.target.com/"
                }

                try:
                    html_resp = requests.get(url, headers=headers, timeout=20)
                    html = html_resp.text or ""
                except Exception as e:
                    print(f"[TARGET HTML FETCH ERROR]: {e}")
                    html = ""

                soup = BeautifulSoup(html, "lxml")
                markdown = soup.get_text("\n", strip=True)

                html_upc = get_upc(html)
                if html_upc:
                    html_upc = normalize_gtin(html_upc)
                    if html_upc:
                        next_specs.append(("gtin", html_upc))
                        print(f"[TARGET HTML GTIN APPENDED]: {html_upc}")
     
                result = type("obj", (), {
                    "success": True,
                    "status_code": 200,
                    "url": url,
                    "html": html,
                    "markdown": None
                })()

            else:
                async with AsyncWebCrawler(config=browser_config) as crawler:
                    result = await crawler.arun(url=url, config=run_config)

                if not result or not result.success:
                    log_crawl(conn, url, "failed")
                    mark_failed(conn, url)
                    return None

                html = result.html or ""
                soup = BeautifulSoup(html, "lxml")

                try:
                    if "target.com" in domain:
                        target_tag = None
                        all_scripts = soup.find_all("script")

                        for script in all_scripts:
                            content = script.string if script.string else ""

                            if "__TGT_DATA__" in content:
                                if "getOwnPropertyNames" in content:
                                    continue

                                if "window.__TGT_DATA__ =" in content or "self.__TGT_DATA__ =" in content:
                                    target_tag = script
                                    print("\n[SUCCESS] Found REAL Target data tag")
                                    break

                        if target_tag:
                            print("\n[TARGET DETECTED - STANDARD]")

                            raw = target_tag.string.strip()
                            data = None

                            start_idx = raw.find("{")
                            end_idx = raw.rfind("}")

                            if start_idx != -1 and end_idx != -1:
                                json_str = raw[start_idx:end_idx + 1]

                                try:
                                    data = json.loads(json_str)
                                except Exception as e:
                                    print(f"[!] Failed to parse Target JSON: {e}")
                                    print("[DEBUG SAMPLE]:", json_str[:200])
                                    data = None
                            else:
                                print("[!] Could not isolate JSON object")

                            if data:
                                next_specs = extract_target_specs(data)

                                print("\n[TARGET SPECS COUNT]:", len(next_specs))
                                if next_specs:
                                    print("[SAMPLE]:", next_specs[:3])
                            else:
                                print("\n[NO PARSEABLE TARGET DATA FOUND]")
                        else:
                            print("\n[NO TARGET DATA FOUND]")

                    elif "walmart.com" in domain:
                        next_data_tag = soup.find("script", id="__NEXT_DATA__")

                        if next_data_tag:
                            print("\n[WALMART DETECTED - STANDARD]")

                            data = json.loads(next_data_tag.string)
                            next_specs = extract_walmart_specs(data)

                            print("\n[WALMART SPECS COUNT]:", len(next_specs))
                            if next_specs:
                                print("[SAMPLE]:", next_specs[:3])
                            else:
                                print("[!] Walmart returned 0 specs")

                            if not next_specs:
                                redux_tag = soup.find("script", id="__WML_REDUX_INITIAL_STATE__")

                                if redux_tag:
                                    print("\n[FOUND REDUX STATE]")

                                    raw = redux_tag.string
                                    if raw.startswith("window.__WML_REDUX_INITIAL_STATE__"):
                                        raw = raw.split("=", 1)[1].strip().rstrip(";")

                                    data = json.loads(raw)
                                    next_specs = extract_walmart_specs(data)

                                    print("\n[REDUX RECURSIVE SPECS COUNT]:", len(next_specs))
                                    if next_specs:
                                        print("[REDUX SAMPLE]:", next_specs[:3])
                                    else:
                                        print("[!] Redux also returned 0.")

                except:
                    pass

                if result.markdown and getattr(result.markdown, "raw_markdown", None):
                    markdown = result.markdown.raw_markdown
                elif result.markdown and getattr(result.markdown, "fit_markdown", None):
                    markdown = result.markdown.fit_markdown
                else:
                    markdown = soup.get_text("\n", strip=True)

        print("\n===== MARKDOWN LENGTH =====")
        print(len(markdown))

        all_specs = []

        for payload in spec_payloads:
            try:
                root = payload.get("data", {})

                product_block = (
                    root.get("productClientOnlyProduct", {}).get("product")
                    or root.get("product")
                    or {}
                )

                groups = product_block.get("specificationGroup", [])

                for group in groups:
                    for spec in group.get("specifications", []):
                        name = spec.get("specName")
                        value = spec.get("specValue")

                        if name and value:
                            all_specs.append((name, value))

            except:
                pass

        seen = set()
        extracted_specs = []

        for name, value in all_specs:
            key = (name.lower(), str(value).lower())
            if key not in seen:
                seen.add(key)
                extracted_specs.append((name, value))

        if extracted_specs:
            print("\n===== API SPECS =====")
            print(extracted_specs[:10])

        json_ld = extract_json_ld_from_html(html)

        def find_product(obj):
            if isinstance(obj, dict):
                t = obj.get("@type")

                if t == "Product" or (isinstance(t, list) and "Product" in t):
                    return obj

                for v in obj.values():
                    result = find_product(v)
                    if result:
                        return result

            elif isinstance(obj, list):
                for item in obj:
                    result = find_product(item)
                    if result:
                        return result

            return None

        product = find_product(json_ld)

        if product:
            products = extract_product_nodes(json_ld)
            for p in products:
                if isinstance(p, dict) and p.get("additionalProperty"):
                    product = p
                    break

        print("\n=== JSON-LD DEBUG ===")
        print("Product found:", bool(product))
        if product:
            print("Keys:", list(product.keys())[:10])
            print("Has additionalProperty:", "additionalProperty" in product)
            print("Count:", len(product.get("additionalProperty", [])))

        print("\n===== STATUS =====")
        print("Success:", result.success if result else False)
        print("Status Code:", result.status_code if result else None)
        print("Final URL:", result.url if result else url)

        gtin = None
        sku = None
        model = None
        title = None
        brand = None
        price = None
        image_url = None

        if product:
            title = product.get("name")

            if isinstance(product.get("brand"), dict):
                brand = product.get("brand", {}).get("name")
            else:
                brand = product.get("brand")

            gtin = (
                product.get("gtin13")
                or product.get("gtin12")
                or product.get("gtin14")
                or product.get("gtin")
                or product.get("upc")
            )

            if gtin is not None:
                gtin = str(gtin).replace(".0", "")

            sku = product.get("sku")
            model = product.get("model") or product.get("mpn")

            offers = product.get("offers")
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                price = clean_price(offers.get("price"))

            img = product.get("image")
            if isinstance(img, list) and len(img) > 0:
                image_url = img[0]
            elif isinstance(img, str):
                image_url = img

        if next_specs or extracted_specs:
            skip_generic_html = True
            print("[STRUCTURED SPECS FOUND - SKIPPING GENERIC HTML]")

        if product and product.get("additionalProperty"):
            print("[SKIPPING GENERIC HTML SPECS - JSON-LD additionalProperty present]")
            combined_specs = extracted_specs + next_specs
        else:
            combined_specs = extracted_specs + next_specs + generic_specs

        identity = {
            "gtin": gtin,
            "model": model,
            "sku": sku,
            "dpci": None
        }


        if html:
            html_upc = get_upc(html)

            if html_upc:
                html_upc = normalize_gtin(html_upc)

            if html_upc:
                if not identity["gtin"]:
                    identity["gtin"] = html_upc
                    print(f"[HTML GTIN FALLBACK] {html_upc}")
                else:
                    print(f"[JSON-LD GTIN PRESERVED] {identity['gtin']}")

                combined_specs.append(("gtin", html_upc))

        hard_ids = extract_hard_ids(html if html else markdown)
        for k, v in hard_ids:
            combined_specs.append((k, v))

        labeled_ids = extract_labeled_ids(markdown)

        for k, v in next_specs:
            if str(k).lower() in ["gtin", "upc"]:
                forced = normalize_gtin(v)

                if forced:
                    if not identity["gtin"]:
                        identity["gtin"] = forced
                        print(f"[API GTIN FALLBACK] {forced}")
                    else:
                        print(f"[JSON-LD GTIN PRESERVED] {identity['gtin']}")

        if not identity["gtin"] and labeled_ids["gtin"]:
            identity["gtin"] = labeled_ids["gtin"]
            print(f"[LABEL GTIN FOUND] {identity['gtin']}")

        if not identity["model"] and labeled_ids["model"]:
            identity["model"] = labeled_ids["model"]
            print(f"[LABEL MODEL FOUND] {identity['model']}")

        fallback_model = None

        if not identity["model"]:
            fallback_model = extract_model_fallback(markdown)

            if is_valid_model(fallback_model) and has_model_support(markdown, fallback_model):
                identity["model"] = fallback_model
                print(f"[MODEL ACCEPTED - FALLBACK] {identity['model']}")
            else:
                print(f"[MODEL REJECTED - FALLBACK] {fallback_model}")

        if (not identity["gtin"] or not identity["model"]) and len(markdown) > 2000:
            llm_ids = run_llm_identity(markdown)

            if llm_ids:
                if llm_ids.get("gtin") and llm_ids["gtin"].isdigit():
                    if not identity["gtin"]:
                        identity["gtin"] = normalize_gtin(llm_ids["gtin"])
                        print(f"[LLM GTIN] {identity['gtin']}")

                if llm_ids.get("model") and is_valid_model(llm_ids["model"]):
                    if not identity["model"]:
                        identity["model"] = llm_ids["model"]
                        print(f"[LLM MODEL] {identity['model']}")

        amazon_gtin = None

        if "amazon.com" in domain:
            for name, value in combined_specs:
                k = str(name).lower()
                val = normalize_gtin(value)

                if k in ["gtin", "upc"] and val:
                    amazon_gtin = val
                    break

            if amazon_gtin:
                print(f"[AMAZON GTIN AUTHORITY] {amazon_gtin}")
                identity["gtin"] = amazon_gtin

        clean_specs = []

        for name, value in combined_specs:
            k = str(name).lower()
            val = str(value).strip()

            if k in ["gtin", "upc"]:
                normalized_val = normalize_gtin(val)

                if normalized_val:

                    is_json_ld_gtin = (
                        product
                        and (
                            normalize_gtin(product.get("gtin13")) == normalized_val
                            or normalize_gtin(product.get("gtin12")) == normalized_val
                            or normalize_gtin(product.get("gtin14")) == normalized_val
                            or normalize_gtin(product.get("gtin")) == normalized_val
                            or normalize_gtin(product.get("upc")) == normalized_val
                        )
                    )

                    if amazon_gtin:
                        if normalized_val != amazon_gtin:
                            print(f"[AMAZON GTIN PRESERVED] {amazon_gtin} ignored={normalized_val}")

                    elif is_json_ld_gtin:
                        if identity["gtin"] != normalized_val:
                            print(f"[JSON-LD GTIN OVERRIDE] {identity['gtin']} -> {normalized_val}")

                        identity["gtin"] = normalized_val

                    elif not identity["gtin"]:
                        identity["gtin"] = normalized_val
                        print(f"[IDENTITY GTIN FALLBACK] {normalized_val}")

                    else:
                        print(f"[GTIN PRESERVED] {identity['gtin']} ignored={normalized_val}")

                else:
                    print(f"[REJECTED GTIN] {val}")

                continue

            elif k in ["model_number", "mpn"]:
                if not identity["model"] and is_valid_model(val):
                    identity["model"] = val
                    print(f"[IDENTITY] MODEL_NUMBER: {val}")
                elif not is_valid_model(val):
                    print(f"[REJECTED MODEL_NUMBER] {val}")
                continue

            elif k == "model":
                if not identity["model"]:
                    if is_valid_model(val) and has_model_support(markdown, val):
                        identity["model"] = val
                        print(f"[MODEL ACCEPTED] {val}")
                    else:
                        print(f"[MODEL REJECTED] {val}")
                continue

            elif k == "sku":
                identity["sku"] = val
                print(f"[IDENTITY] SKU: {val}")
                continue

            clean_specs.append((name, value))

        combined_specs = clean_specs

        if not identity["gtin"]:
            for name, value in combined_specs:
                k = str(name).lower()
                val = str(value).strip()

                if k in ["gtin", "upc"]:
                    if val.isdigit() and 12 <= len(val) <= 14:
                        identity["gtin"] = val
                        print(f"[FINAL GTIN] {val}")
                        break

        if product and product.get("additionalProperty"):
            for p in product["additionalProperty"]:
                if not isinstance(p, dict):
                    continue

                name = p.get("name")
                value = p.get("value")

                if name and value:
                    combined_specs.append((name, value))

        print("\n=== DEBUG: BEFORE process_product ===")
        print("combined_specs len:", len(combined_specs))
        print("markdown len:", len(markdown) if markdown else 0)
        print("product exists:", bool(product))

        if is_identity_mode and not is_rebuild_mode:
            print("[UNRESOLVED] skipping spec extraction")
            structured = []

        else:
            structured_input = None

            if combined_specs:
                structured_input = [
                    {
                        "source_label": name,
                        "source_value": value
                    }
                    for name, value in combined_specs
                ]

            print(
                f"[PROCESS_PRODUCT INPUT] combined_specs={len(combined_specs)} "
                f"structured_input={len(structured_input or [])} "
                f"skip_llm={False if is_rebuild_mode else bool(structured_input)}"
            )

            structured = process_product(
                product_json=product,
                markdown=markdown,
                category=category,
                skip_llm=False if is_rebuild_mode else bool(structured_input),
                structured_input=structured_input
            )

            structured = list(structured or [])


        print("\n=== DEBUG: AFTER process_product ===")
        print("structured len:", len(structured))
        print("structured sample:", structured[:5])

        print("\n=== FINAL STRUCTURED CLAIMS ===")
        for attr, data in structured[:15]:
            print(attr, "=>", data)

        filtered = []

        for attr, data in structured:
            if attr in {"gtin", "model", "sku", "mpn", "upc", "dpci", "model_number"}:
                print(f"[POST-FILTER REMOVED] {attr}: {data}")
                continue
            filtered.append((attr, data))

        structured = filtered

        print(f"[POST FILTER CLAIM COUNT] {len(structured)}")

        gtin = normalize_gtin(identity["gtin"])
        model = identity["model"]
        sku = identity["sku"]

        if not model:
            model = None

        if not sku:
            sku = extract_sku_from_text(markdown, html)

        def is_duplicate_sku(conn, domain, sku):
            if not sku or not domain:
                return False

            row = conn.execute("""
                SELECT 1
                FROM crawled_pages cp
                JOIN raw_claims rc ON rc.page_id = cp.id
                JOIN sources s ON rc.source_id = s.id
                WHERE s.domain = ?
                AND rc.attribute = 'sku'
                AND rc.value_string = ?
                LIMIT 1
            """, (domain, sku)).fetchone()
 
            return bool(row)


        if not is_rebuild_mode and is_duplicate_sku(conn, domain, sku):
            print(f"[DEDUP SKIP] {domain} | SKU={sku} | URL={url}")

            mark_complete(conn, url)

            return {"skipped": True}

        source_type = get_source_type(conn, url)
        pillar_count = get_pillar_count(structured, category)

        print("\n=== DEBUG: FILTER CHECK ===")
        print("source_type:", source_type)
        print("pillar_count:", pillar_count)

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

            print(f"[MATCHED PRODUCT ROW] id={existing['id']} gtin={existing['gtin']} model={existing['model']}")

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

                    print(f"[GTIN VERIFY] incoming={gtin} existing={existing_gtin} similarity={similarity:.2f}")

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

                        return {"skipped": True}

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

                    return {"skipped": True}

            record_id = gtin or existing_gtin or existing_id
        else:
            if identity["gtin"]:
                record_id = identity["gtin"]
            elif identity["model"]:
                record_id = identity["model"]
            elif identity["sku"]:
                record_id = identity["sku"]
            else:
                record_id = url

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

        if not gtin and not model:
            print("[UNRESOLVED] Attempting immediate search bridge")

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
            """, (title or "", model or "")).fetchone()

            if resolved:
                gtin = normalize_gtin(resolved["gtin"])
                model = resolved["model"]

                record_id = gtin or model

                print(f"[RESOLVED AFTER SEARCH] GTIN={gtin} MODEL={model}")

            if not gtin and not model:
                print("[STILL UNRESOLVED] marking unresolved")

                mark_unresolved(conn, url)

                return {"skipped": True}
        if gtin and not is_rebuild_mode:

            conn.execute("""
                UPDATE raw_claims
                SET product_id=?
                WHERE product_id=?
                   OR product_id=?
                   OR product_id=?
            """, (gtin, url, model, sku))

            conn.execute("""
                UPDATE raw_claims
                SET product_id=?
                WHERE page_id IN (
                    SELECT id
                    FROM crawled_pages
                    WHERE url=?
                )
            """, (gtin, url))

            print(f"[BACKFILL → GTIN] {url} / {model} / {sku} → {gtin}")
 
        if is_rebuild_mode:
            old_pages = conn.execute("""
                SELECT id
                FROM crawled_pages
                WHERE url=?
            """, (url,)).fetchall()

            for row in old_pages:
                print(f"[REBUILD DELETE] old_page_id={row['id']}")

                conn.execute("""
                    DELETE FROM raw_claims
                    WHERE page_id=?
                """, (row["id"],))

        crawl_id = log_crawl(conn, url, "success")

        page_existing = conn.execute("""
            SELECT 1 FROM raw_claims
            WHERE page_id = ?
            LIMIT 1
        """, (crawl_id,)).fetchone()

        if page_existing and not is_rebuild_mode:
            print(f"[SKIP INSERT - ALREADY PROCESSED PAGE] {url}")
            mark_complete(conn, url)
            return {"skipped": True} 

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

        if structured:
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
                        if math_val.lower() in ["not specified", "n/a", "unknown"]:
                            math_val = None

                if display and str(display).lower() in ["not specified", "n/a", "unknown", ""]:
                    continue

                if attr == "upc":
                    if display:
                        display = str(display).replace(".0", "")
                    math_val = None
                    unit = "text"

                print(f"[INSERT] {attr} | {display} | unit={unit} | math={math_val}")

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

        if gtin or model:
            if existing:
                product_payload = {
                    "model": existing["model"] or model,
                    "brand": existing["brand"] or brand,
                    "title": existing["title"] or title,
                    "price": price,
                    "image_url": existing["image_url"] or image_url,
                    "gtin": gtin
                }
            else:
                product_payload = {
                    "model": model,
                    "brand": brand,
                    "title": title,
                    "price": price,
                    "image_url": image_url,
                    "gtin": gtin
                }

            upsert_product(conn, product_payload)

            structured_identity_found = bool(
                gtin
                or (
                    model
                    and product
                )
                or (
                    next_specs
                    and (
                        gtin or model
                    )
                )
            )

            if structured_identity_found:

                print("\n[CASE A] STRUCTURED IDENTITY FOUND")
                print("[POST-IDENTITY SEARCH BRIDGE - TOP 3 MODE]")

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

            else:

                print("\n[CASE B] NO STRUCTURED IDENTITY")
                print("[SINGLE URL MODE]")

                first_domain_row = conn.execute("""
                    SELECT 1
                    FROM crawled_pages cp
                    JOIN sources s
                      ON s.domain = ?
                    LIMIT 1
                """, (domain,)).fetchone()

                if not first_domain_row:

                    save_url(
                        conn,
                        url,
                        category=category,
                        priority=10,
                        provider="fallback"
                    )

                    print(f"[SAVED SINGLE FALLBACK URL] {url}")

            print("\n=== UPSERT PRODUCT ===")
            print(product_payload)

            cleaned_price = clean_price(price)

            if gtin and cleaned_price:
                print(f"[PRICE INSERT] {gtin} | {cleaned_price} | {domain}")

                upsert_price(conn, {
                    "gtin": gtin,
                    "domain": domain,
                    "price": cleaned_price,
                    "url": url
                })

        if is_identity_mode and not is_rebuild_mode:
            print("[GTIN BEFORE SEARCH BRIDGE]:", gtin)
            print("\n=== TRIGGER SEARCH BRIDGE ===")

        print("\n" + "="*80)
        print(f"[MINER COMPLETE] {url}")
        print(f"[FINAL GTIN] {gtin}")
        print(f"[FINAL MODEL] {model}")
        print(f"[CLAIMS INSERTED] {len(structured)}")
        print("="*80)

        if is_identity_mode and (gtin or model) and not is_rebuild_mode:
            print("[RESOLVED AFTER UNRESOLVED] marking complete")

            print("[SEARCH BRIDGE INPUT]", {
                "gtin": gtin,
                "model": model,
                "sku": sku,
                "brand": brand,
                "title": title
            })

            before_gtin = gtin
            before_model = model
 
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

            refreshed = conn.execute("""
                SELECT gtin, model
                FROM products
                WHERE
                    (gtin IS NOT NULL AND gtin = ?)
                    OR (
                        model IS NOT NULL
                        AND lower(model) = lower(?)
                    )
                LIMIT 1
            """, (gtin or "", model or "")).fetchone()

            if refreshed:
                new_gtin = normalize_gtin(refreshed["gtin"])
                new_model = refreshed["model"]

                gained_gtin = not before_gtin and new_gtin
                gained_model = not before_model and new_model

                if gained_gtin or gained_model:
                    print("[SECOND SEARCH BRIDGE PASS]")
                    print("gtin:", new_gtin)
                    print("model:", new_model)

                    run_search_bridge(conn, {
                        "gtin": new_gtin,
                        "model": new_model,
                        "sku": sku,
                        "brand": brand,
                        "title": title,
                        "price": price,
                        "image_url": image_url,
                        "category": category
                    })

            mark_complete(conn, url)

            return {
                "gtin": gtin,
                "model": model,
                "needs_enrichment": False,
                "claims_found": 0
            }

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