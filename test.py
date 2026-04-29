import asyncio
import json
import re
import ast
import requests
from bs4 import BeautifulSoup

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig

from miner import extract_product_nodes, extract_json_ld_claims, clean_price, extract_json_ld_from_html
from brain import process_product, PILLARS
from db import get_db, insert_claim, upsert_product, log_crawl
from urllib.parse import urlparse
from playwright.async_api import async_playwright
import random
from config import HIGH_SECURITY_DOMAINS, HEAVY_JS_DOMAINS
from scout import fetch_with_retry


URL = "https://www.energystar.gov/productfinder/product/certified-residential-refrigerators/details/2317778"

CATEGORY = "mini_fridges"


def clean_html(text):
    if not text:
        return ""

    clean = re.sub(r'<.*?>', '', text)

    if ":" in clean:
        parts = clean.split(":", 1)
        if len(parts[0]) < 40:
            clean = parts[1]

    return clean.strip()


def normalize_domain(url: str) -> str:
    domain = urlparse(url).netloc.lower().replace("www.", "")
    parts = domain.split(".")
    if len(parts) >= 2:
        domain = ".".join(parts[-2:])
    return domain


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
        product = data.get('data', {}).get('product', {})
        item = product.get('item', {})
        description = item.get('product_description', {})

        specs = description.get('soft_specifications', {}).get('specifications', [])
        for s in specs:
            label = s.get('label')
            value = s.get('value')
            if label and value:
                results.append((clean_html(label), clean_html(value)))

        bullets = description.get('bullet_descriptions', [])
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
    match = re.search(r'/A-(\d+)', url)
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

        product_item = data.get('data', {}).get('product', {}).get('item', {})
        upc = product_item.get('primary_barcode')

        if upc:
            print(f"[FOUND UPC]: {upc}")
            next_specs = extract_target_specs(data)
            next_specs.append(("UPC", upc))
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


def get_pillar_count(structured, category):
    pillar_keys = PILLARS.get(category, [])
    return sum(1 for k, _ in structured if k in pillar_keys)


def get_source_type(conn, url):
    domain = normalize_domain(url)

    row = conn.execute(
        "SELECT source_type FROM sources WHERE domain=?",
        (domain,)
    ).fetchone()

    if row:
        return row["source_type"]

    return "unknown"


async def test():
    raw_domain = urlparse(URL).netloc.lower()
    domain = normalize_domain(URL)

    is_heavy_js = any(d in raw_domain for d in HEAVY_JS_DOMAINS)
    use_cdp = any(d in raw_domain for d in HIGH_SECURITY_DOMAINS)

    print(f"[ROUTING] {'CDP' if use_cdp else 'STANDARD'} -> {raw_domain}")

    browser_config = BrowserConfig(
        browser_type="chromium",
        headless=False
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

    spec_payloads = []
    next_specs = []

    if use_cdp:
        if "homedepot.com" in domain:
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

                await page.goto(URL)
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

            result = type("obj", (), {"success": True, "status_code": 200, "url": URL, "html": html, "markdown": None})()

        else:
            if "target.com" in domain:
                print("\n[USING TARGET REDSKY API]")
                next_specs = get_target_specs_direct(URL)

                print("\n[TARGET SPECS COUNT]:", len(next_specs))
                if next_specs:
                    print("[SAMPLE]:", next_specs[:3])
                else:
                    print("[!] Target API returned 0 specs")

                html = ""
                markdown = ""
                result = type("obj", (), {"success": True, "status_code": 200, "url": URL, "html": html, "markdown": None})()

            else:
                async with async_playwright() as p:
                    browser = await p.chromium.connect_over_cdp("http://localhost:9222")
                    context = browser.contexts[0]
                    page = context.pages[0] if context.pages else await context.new_page()

                    await page.goto(URL)
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

                result = type("obj", (), {"success": True, "status_code": 200, "url": URL, "html": html, "markdown": None})()

    else:
        if "target.com" in domain:
            print("\n[USING TARGET REDSKY API]")
            next_specs = get_target_specs_direct(URL)

            print("\n[TARGET SPECS COUNT]:", len(next_specs))
            if next_specs:
                print("[SAMPLE]:", next_specs[:3])
            else:
                print("[!] Target API returned 0 specs")

            html = ""
            markdown = ""
            result = type("obj", (), {"success": True, "status_code": 200, "url": URL, "html": html, "markdown": None})()

        else:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url=URL, config=run_config)

            if not result or not result.success:
                print("\n===== ERROR =====")
                print(result.error_message if result else "No result returned")
                return

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

    print("\n=== JSON-LD DEBUG ===")
    print("Product found:", bool(product))
    if product:
        print("Keys:", list(product.keys())[:10])
        print("Has additionalProperty:", "additionalProperty" in product)
        print("Count:", len(product.get("additionalProperty", [])))

    print("\n===== STATUS =====")
    print("Success:", result.success)
    print("Status Code:", result.status_code)
    print("Final URL:", result.url)

    gtin = None
    sku = None
    model = None

    if product:
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

    price = None
    if product:
        offers = product.get("offers")
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            price = clean_price(offers.get("price"))

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
        category=CATEGORY,
        skip_llm=True if combined_specs else False,
        structured_input=combined_specs if combined_specs else None
    )
    structured = list(structured or [])

    print("\n=== DEBUG: AFTER process_product ===")
    print("structured len:", len(structured))
    print("structured sample:", structured[:5])

    if not gtin:
        for attr, data in structured:
            if attr == "upc":
                gtin = str(data.get("display") or data.get("math") or "").replace(".0", "")
                break

    conn = get_db()

    pillar_count = get_pillar_count(structured, CATEGORY)
    source_type = get_source_type(conn, URL)

    print("\n=== DEBUG: FILTER CHECK ===")
    print("source_type:", source_type)
    print("pillar_count:", pillar_count)

    if source_type == "manufacturer" and pillar_count < 2:
        print("\n=== BLOCKED (MANUFACTURER LOW QUALITY) ===")
        print("structured:", structured[:10])
        with open("failed_manufacturer_urls.txt", "a") as f:
            f.write(URL + "\n")
        conn.close()
        return

    if gtin:
        gtin = str(gtin).replace(".0", "")
        product_id = gtin
    else:
        product_id = model or sku or URL
  
    if product:
        product["model"] = product_id
        product["price"] = price

        if isinstance(product.get("brand"), dict):
            product["brand"] = product["brand"].get("name")

        img = product.get("image")

        if isinstance(img, list) and len(img) > 0:
            product["image_url"] = img[0]
        elif isinstance(img, str):
            product["image_url"] = img
        else:
            product["image_url"] = None

        product["gtin"] = gtin

        upsert_product(conn, product)

    domain = normalize_domain(URL)

    page_id = log_crawl(conn, URL, "success")

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

        if display and display.lower() in ["not specified", "n/a", "unknown", ""]:
            continue

        if attr == "upc":
            if display:
                display = str(display).replace(".0", "")
            math_val = None
            unit = "text"

        insert_claim(
            conn,
            page_id,
            source_id,
            attr,
            display,
            product_id=product_id,
            value_numeric=math_val,
            unit=unit
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    asyncio.run(test())