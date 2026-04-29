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
from db import get_db, insert_claim, mark_complete, mark_failed, upsert_product, upsert_price, log_crawl
from search_bridge import run_search_bridge
from config import HIGH_SECURITY_DOMAINS, HEAVY_JS_DOMAINS
from scout import fetch_with_retry


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


def extract_model_from_text(markdown, html):
    text = f"{markdown or ''}\n{html or ''}"

    model_match = re.search(
        r"(?:Model\s*#|MPN)\s*[:\-]?\s*([A-Z0-9\-]{5,})",
        text,
        re.IGNORECASE
    )

    if not model_match:
        return None

    candidate = model_match.group(1).strip()
    return candidate if not candidate.isdigit() else None


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


def clean_html(text):
    if not text:
        return ""

    clean = re.sub(r"<.*?>", "", text)

    if ":" in clean:
        parts = clean.split(":", 1)
        if len(parts[0]) < 40:
            clean = parts[1]

    return clean.strip()


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

        product_item = data.get("data", {}).get("product", {}).get("item", {})
        upc = product_item.get("primary_barcode")

        next_specs = extract_target_specs(data)

        if upc:
            print(f"[FOUND UPC]: {upc}")
            next_specs.append(("UPC", upc))

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

        print("[TARGET RAW JSON KEYS]:", data.keys())
        print("[TARGET PRODUCT KEYS]:", data.get("data", {}).get("product", {}).keys())

        return extract_target_specs(data)

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


async def run_miner(url, category):
    conn = get_db()

    row = conn.execute(
        "SELECT status FROM crawled_pages WHERE url=?",
        (url,)
    ).fetchone()

    if row and row["status"] == "failed":
        print(f"[SKIP FAILED] {url}")
        conn.close()
        return {"skipped": True}

    if ".pdf" in url.lower():
        print(f"[SKIP PDF] {url}")
        mark_complete(conn, url)
        conn.commit()
        conn.close()
        return {"skipped": True}

    try:
        raw_domain = urlparse(url).netloc.lower()
        domain = normalize_domain(url)

        is_heavy_js = any(d in raw_domain for d in HEAVY_JS_DOMAINS)
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
                    if next_specs:
                        print("[SAMPLE]:", next_specs[:3])
                    else:
                        print("[!] Target API returned 0 specs")

                    html = ""
                    markdown = ""
                    result = type("obj", (), {"success": True, "status_code": 200, "url": url, "html": html, "markdown": None})()

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

                    markdown = soup.get_text("\n", strip=True)

                    result = type("obj", (), {"success": True, "status_code": 200, "url": url, "html": html, "markdown": None})()

        else:
            if "target.com" in domain:
                print("\n[USING TARGET REDSKY API]")
                next_specs = get_target_specs_direct(url)

                print("\n[TARGET SPECS COUNT]:", len(next_specs))
                if next_specs:
                    print("[SAMPLE]:", next_specs[:3])
                else:
                    print("[!] Target API returned 0 specs")

                html = ""
                markdown = ""
                result = type("obj", (), {"success": True, "status_code": 200, "url": url, "html": html, "markdown": None})()

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

        combined_specs = extracted_specs + next_specs

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

        structured = process_product(
            product_json=product,
            markdown=markdown,
            category=category,
            skip_llm=True if combined_specs else False,
            structured_input=combined_specs if combined_specs else None
        )
        structured = list(structured or [])

        print("\n=== DEBUG: AFTER process_product ===")
        print("structured len:", len(structured))
        print("structured sample:", structured[:5])

        print("\n=== FINAL STRUCTURED CLAIMS ===")
        for attr, data in structured[:15]:
            print(attr, "=>", data)

        if not gtin:
            for attr, data in structured:
                if attr == "upc":
                    gtin = str(data.get("display") or data.get("math") or "").replace(".0", "")
                    break

        gtin = normalize_gtin(gtin)

        if not model:
            model = extract_model_from_text(markdown, html)

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


        if is_duplicate_sku(conn, domain, sku):
            print(f"[DEDUP SKIP] {domain} | SKU={sku} | URL={url}")

            mark_complete(conn, url)

            return {"skipped": True}

        source_type = get_source_type(conn, url)
        pillar_count = get_pillar_count(structured, category)

        print("\n=== DEBUG: FILTER CHECK ===")
        print("source_type:", source_type)
        print("pillar_count:", pillar_count)

        if source_type == "manufacturer" and pillar_count < 2:
            log_crawl(conn, url, "failed")
            mark_complete(conn, url)
            return {"skipped": True}
 
        if not structured and source_type == "manufacturer":
            log_crawl(conn, url, "failed")
            mark_failed(conn, url)
            return None

        existing = None

        if gtin:
            existing = conn.execute(
                "SELECT * FROM products WHERE gtin=?",
                (gtin,)
            ).fetchone()

        if not existing and model and brand:
            existing = conn.execute(
                "SELECT * FROM products WHERE model=? AND brand=?",
                (model, brand)
            ).fetchone()

        if existing:
            existing_id = existing["model"]

            print("\n=== EXISTING PRODUCT FOUND ===")
            print("existing_id:", existing_id)
            print("existing_gtin:", existing["gtin"])

            if gtin and not existing["gtin"]:
                print("\n=== GTIN BACKFILL ===")
                print("old_id:", existing_id)
                print("new_gtin:", gtin)

                conn.execute(
                    "UPDATE products SET gtin=? WHERE model=?",
                    (gtin, existing_id)
                )

                conn.execute(
                    "UPDATE raw_claims SET product_id=? WHERE product_id=?",
                    (gtin, existing_id)
                )

            record_id = gtin or existing["gtin"] or existing_id
        else:
            record_id = gtin if gtin else (model if model else (sku if sku else url))

        print("\n=== FINAL IDENTITY ===")
        print("GTIN:", gtin)
        print("MODEL:", model)
        print("SKU:", sku)
        print("BRAND:", brand)
        print("TITLE:", title)
        print("RECORD ID:", record_id)

        if gtin:
            conn.execute("""
                UPDATE raw_claims
                SET product_id=?
                WHERE product_id IN (?, ?)
            """, (gtin, model, sku))
 
        crawl_id = log_crawl(conn, url, "success")

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

        if product:
            if existing:
                product_payload = {
                    "model": existing["model"] or model,
                    "brand": existing["brand"] or brand,
                    "title": existing["title"] or title,
                    "price": price,
                    "image_url": existing["image_url"] or image_url,
                    "gtin": gtin or existing["gtin"]
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

        print("[GTIN BEFORE SEARCH BRIDGE]:", gtin)
        print("\n=== TRIGGER SEARCH BRIDGE ===")

        if gtin:
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

        mark_complete(conn, url)
        return {"gtin": gtin, "claims_found": len(structured)}

    except Exception:
        import traceback
        traceback.print_exc()
        log_crawl(conn, url, "failed")
        mark_failed(conn, url)
        return None

    finally:
        conn.commit()
        conn.close()