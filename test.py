import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import re
import ast
import requests
from bs4 import BeautifulSoup
import brain
print(brain.__file__)

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig

from miner import extract_product_nodes, extract_json_ld_claims, clean_price, extract_json_ld_from_html
from brain import process_product, PILLARS
from db import get_db, insert_claim, upsert_product, log_crawl
from urllib.parse import urlparse
from playwright.async_api import async_playwright
import random
from config import HIGH_SECURITY_DOMAINS, HEAVY_JS_DOMAINS, INTERACTIVE_DOMAINS
from scout import fetch_with_retry


URL = "https://www.target.com/p/apple-macbook-neo-a18-pro-2026-laptop-256gb-indigo/-/A-91122085"

CATEGORY = "laptops"

WRITE_TO_DB = False

if not WRITE_TO_DB:
    print("[DB DISABLED] All DB writes are no-ops")

    def get_db():
        class DummyConn:
            def execute(self, *args, **kwargs): return self
            def fetchone(self): return None
            def fetchall(self): return []
            def commit(self): pass
            def close(self): pass
        return DummyConn()

    def insert_claim(*args, **kwargs): pass
    def upsert_product(*args, **kwargs): pass

    def log_crawl(*args, **kwargs):
        return 0


def clean_html(text):
    if not text:
        return ""

    clean = re.sub(r'<.*?>', '', text)

    if ":" in clean:
        parts = clean.split(":", 1)
        if len(parts[0]) < 40:
            clean = parts[1]

    return clean.strip()


def is_identity(attr, data):
    attr = str(attr).lower().strip()

    return attr in {
        "gtin",
        "model",
        "mpn",
        "upc",
        "sku",
        "dpci"
    }


def extract_labeled_ids(markdown):
    identity = {
        "gtin": None,
        "model": None
    }

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


def get_target_tcin(url):
    match = re.search(r'/A-(\d+)', url)
    return match.group(1) if match else None


async def get_target_specs_browser(page, url):
    tcin = get_target_tcin(url)
    if not tcin:
        print("[TARGET API ERROR]: Could not extract TCIN from URL")
        return []

    try:
        data = await page.evaluate(
            """
            async ({ tcin }) => {
                const params = new URLSearchParams({
                    key: "9f36aeafbe60771e321a7cc95a78140772ab3e96",
                    tcin: tcin,
                    store_id: "3991",
                    pricing_store_id: "3991",
                    has_pricing_store_id: "true",
                    is_bot: "false"
                });

                const res = await fetch(
                    "https://redsky.target.com/redsky_aggregations/v1/web/pdp_client_v1?" + params.toString(),
                    {
                        method: "GET",
                        credentials: "include",
                        headers: {
                            "accept": "application/json"
                        }
                    }
                );

                return await res.json();
            }
            """,
            {"tcin": tcin}
        )

        print("[TARGET BROWSER API KEYS]:", data.keys())
        print("[TARGET BROWSER PRODUCT KEYS]:", data.get("data", {}).get("product", {}).keys())

        return extract_target_specs(data)

    except Exception as e:
        print(f"[TARGET BROWSER API ERROR]: {e}")
        return []


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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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

        next_specs = extract_target_specs(data)

        product_item = data.get('data', {}).get('product', {}).get('item', {})
        upc = product_item.get('primary_barcode')

        if upc:
            print(f"[FOUND UPC]: {upc}")
            next_specs.append(("gtin", str(upc)))
            return next_specs

        try:
            html_resp = requests.get(url, headers=headers, timeout=15)
            html = html_resp.text

            html_upc = get_upc(html)
            if html_upc:
                next_specs.append(("gtin", html_upc))

        except Exception as e:
            print(f"[HTML FETCH ERROR]: {e}")

        print("[TARGET RAW JSON KEYS]:", data.keys())
        print("[TARGET PRODUCT KEYS]:", data.get("data", {}).get("product", {}).keys())

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


async def test():
    html = ""
    markdown = ""
    result = None
    raw_domain = urlparse(URL).netloc.lower()
    domain = normalize_domain(URL)

    is_heavy_js = any(d in raw_domain for d in HEAVY_JS_DOMAINS)
    is_interactive = any(d in raw_domain for d in INTERACTIVE_DOMAINS)
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

    if "target.com" in domain:
        print("[TARGET OVERRIDE ENABLED]")

        wait_for = """
        js:() => {
            const text = document.body.innerText.toLowerCase();
            return (
                text.includes("upc") ||
                text.includes("item number") ||
                text.includes("dpci")
            );
        }
        """

        DEFAULT_JS = """
        (async () => {
            for (let i = 0; i < 6; i++) {
                window.scrollTo(0, document.body.scrollHeight);
                await new Promise(r => setTimeout(r, 1500));
            }
        })();
        """

        delay = 8.0

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
    generic_specs = []
    extracted_specs = []
    skip_generic_html = False

    if "target.com" in domain:
        print("\n[USING TARGET REDSKY API]")

        next_specs = get_target_specs_direct(URL)

        print("\n[TARGET SPECS COUNT]:", len(next_specs))
        if next_specs:
            print("[SAMPLE]:", next_specs[:3])
        else:
            print("[!] Target API returned 0 specs")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
            "Referer": "https://www.target.com/"
        }

        try:
            html_resp = requests.get(URL, headers=headers, timeout=20)
            html = html_resp.text or ""
        except Exception as e:
            print(f"[TARGET HTML FETCH ERROR]: {e}")
            html = ""

        soup = BeautifulSoup(html, "lxml")
        markdown = soup.get_text("\n", strip=True)

        result = type("obj", (), {
            "success": True,
            "status_code": 200,
            "url": URL,
            "html": html,
            "markdown": None
        })()

    elif "homedepot.com" in domain:
        print("\n[HOME DEPOT CDP MODE]")

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

            await page.wait_for_timeout(8000)
            html = await page.content()

        soup = BeautifulSoup(html, "lxml")
        markdown = soup.get_text("\n", strip=True)

        result = type("obj", (), {
            "success": True,
            "status_code": 200,
            "url": URL,
            "html": html,
            "markdown": None
        })()

    elif use_cdp and is_interactive:
        print("\n[INTERACTIVE CDP MODE]")

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

            print("\n[EXPANDING ACCORDIONS]")

            await page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight)
            """)

            await page.wait_for_timeout(1500)

            await page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight / 2)
            """)

            await page.wait_for_timeout(1500)

            for _ in range(2):
                await page.mouse.wheel(0, 2500)
                await page.wait_for_timeout(750)

            spec_selector = "text=/Specifications/i"

            count = await page.locator(spec_selector).count()

            print("[SPEC COUNT]", count)

            all_spec_nodes = await page.locator("text=/spec/i").all_inner_texts()

            print("[SPEC TEXT MATCHES]")
            print(all_spec_nodes[:20])

            spec_container = None

            if count > 0:

                print("[SPEC TEXT FOUND]")

                spec_container = None

                try:
                    spec = page.locator(spec_selector).first

                    text = await spec.inner_text()

                    print("[CLICK TARGET]", text[:120])

                    button = spec.locator(
                        "xpath=ancestor::*[@role='button' or self::button or self::summary][1]"
                    )

                    if await button.count() == 0:
                        button = spec

                    accordion_selectors = [
                        ".product-specification__heading",
                        "[class*=accordion]",
                        "[class*=collapse]",
                        "[class*=expand]",
                        "[aria-expanded]",
                        "summary",
                        "button"
                    ]

                    heading = None

                    for selector in accordion_selectors:

                        try:
                            loc = page.locator(selector).filter(
                                has_text=re.compile("spec", re.I)
                            ).first

                            if await loc.count() > 0:
                                heading = loc
                                print(f"[ACCORDION FOUND] {selector}")
                                break

                        except:
                            pass
 
                    if heading:

                        try:
                            cls = (await heading.get_attribute("class") or "").lower()
                            print("[SPEC HEADING CLASS]", cls)
                        except:
                            cls = ""

                        await heading.scroll_into_view_if_needed()

                        try:
                            await heading.click(force=True)
                            print("[SPEC EXPANDED]")
                        except Exception as e:
                            print("[SPEC CLICK FAILED]", e)

                    await page.wait_for_timeout(2500)

                    container_selectors = [
                        ".product-specification",
                        "[class*=spec]",
                        "[id*=spec]",
                        "[data-testid*=spec]"
                    ]

                    spec_container = None

                    for selector in container_selectors:

                        try:
                            loc = page.locator(selector).first

                            if await loc.count() == 0:
                                continue
 
                            text = await loc.inner_text()
  
                            if len(text) > 300:
                                spec_container = loc
                                print(f"[SPEC CONTAINER FOUND] {selector}")
                                break

                        except:
                            pass

                    last_count = 0

                    for _ in range(10):

                        try:
                            buttons = page.locator(
                                ".sony-btn:has-text('See More')"
                            ) 

                            btn = buttons.last

                            if await btn.count() == 0:
                                break

                            if not await btn.is_visible():
                                break

                            old_html = await spec_container.inner_html()

                            await btn.click(force=True, timeout=2000)

                            await page.mouse.wheel(0, 3000)
                            await page.wait_for_timeout(1500)

                            await page.wait_for_function(
                                """({selector, oldHtml}) => {
                                    const el = document.querySelector(selector);
                                    return el && el.innerHTML !== oldHtml;
                                }""",
                                arg={
                                    "selector": ".product-specification__content",
                                    "oldHtml": old_html
                                },
                                timeout=5000
                            )

                            card_count = await page.locator(
                                ".full-specifications__specifications-single-card"
                            ).count()

                            print(f"[SEE MORE CLICKED] cards={card_count}")

                            if card_count <= last_count:
                                print("[NO NEW CARDS LOADED]")
                                break

                            last_count = card_count

                        except Exception as e:
                            print("[SEE MORE WAIT TIMEOUT]", e)

                            card_count = await page.locator(
                                ".full-specifications__specifications-single-card"
                            ).count()

                            print(f"[CURRENT CARD COUNT] {card_count}")

                            if card_count <= last_count:
                                print("[NO NEW CARDS LOADED]")
                                break

                            last_count = card_count
                            continue

                    count = await spec_container.count()

                    print("[SPEC CONTAINER COUNT]", count)

                    if count > 0:

                        text = await spec_container.inner_text()

                        print("\n=== SPEC CONTAINER PREVIEW ===")
                        print(text[:3000])

                    await page.wait_for_timeout(4000)

                    final_card_count = await page.locator(
                        ".full-specifications__specifications-single-card"
                    ).count()

                    print(f"[FINAL CARD COUNT] {final_card_count}")

                    await page.wait_for_timeout(5000)

                    if not spec_container:
                        raise Exception("No spec container found")

                    await page.wait_for_timeout(2000)

                    html = await spec_container.evaluate("(el) => el.outerHTML")

                    print("[USING ISOLATED SPEC HTML]")
                    print(f"[POST-EXPANSION HTML LEN] {len(html)}")

                    possible_selectors = [
                        '[data-testid*="spec"]',
                        '[class*="spec"]',
                        '[id*="spec"]',
                        '[aria-labelledby*="spec"]',
                        '[aria-label*="spec"]',
                    ]

                    for selector in possible_selectors:

                        loc = page.locator(selector)

                        try:
                            count = await loc.count()

                            for i in range(count):
       
                                el = loc.nth(i)

                                text = await el.inner_text()
     
                                if len(text) > 300:
                                    spec_container = el
                                    print(f"[SPEC CONTAINER FOUND] {selector}")
                                    break

                            if spec_container:
                                break

                        except Exception as e:
                            print("[SPEC SELECTOR ERROR]", e)

                    try:
                        await page.wait_for_selector(
                            "table, dl, .specifications, .product-specs",
                            timeout=4000
                        )
                        print("[SPEC CONTENT LOADED]")
                    except:
                        print("[SPEC CONTENT WAIT TIMEOUT]")

                except Exception as e:
                    print("[SPEC CLICK ERROR]", e)

            else:
                print("[SPEC TEXT NOT FOUND]")
        
        generic_specs = []

        soup = BeautifulSoup(html, "lxml")

        spec_root = BeautifulSoup(html, "lxml")

        generic_specs = []

        tables = spec_root.find_all("table")

        generic_specs = []

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

        cards = spec_root.select(
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

        print(f"[GENERIC HTML SPECS] {len(generic_specs)}")
        print(generic_specs[:15])

        soup = BeautifulSoup(html, "lxml")
        markdown = soup.get_text("\n", strip=True)

        result = type("obj", (), {
            "success": True,
            "status_code": 200,
            "url": URL,
            "html": html,
            "markdown": None
        })()

    elif use_cdp:
        print("\n[PASSIVE CDP MODE]")

        if "walmart.com" in domain:
            print("\n[WALMART DETECTED - CDP]")
  
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

            await page.wait_for_timeout(3000)

            await page.evaluate("""
            window.scrollTo(0, document.body.scrollHeight)
            """)

            await page.wait_for_timeout(5000)

            html = await page.content()

            soup = BeautifulSoup(html, "lxml")

            if "walmart.com" in domain:

                next_data_tag = soup.find("script", id="__NEXT_DATA__")

                if next_data_tag:

                    try:
                        data = json.loads(next_data_tag.string)
                        next_specs = extract_walmart_specs(data)
                    except Exception as e:
                        print(f"[WALMART NEXT_DATA ERROR]: {e}")
                        next_specs = []

                    print("\n[WALMART SPECS COUNT]:", len(next_specs))

                    if not next_specs:

                        redux_tag = soup.find(
                            "script",
                            id="__WML_REDUX_INITIAL_STATE__"
                        )

                        if redux_tag:

                            try:
                                raw = redux_tag.string

                                if raw.startswith(
                                    "window.__WML_REDUX_INITIAL_STATE__"
                                ):
                                    raw = raw.split("=", 1)[1].strip().rstrip(";")

                                data = json.loads(raw)

                                next_specs = extract_walmart_specs(data)

                            except Exception as e:
                                print(f"[WALMART REDUX ERROR]: {e}")
                                next_specs = []

        soup = BeautifulSoup(html, "lxml")

        skip_generic_html = bool(next_specs or extracted_specs)

        if skip_generic_html:
            print("[STRUCTURED SPECS FOUND - SKIPPING GENERIC HTML]")

        generic_specs = []

        if not skip_generic_html:
            tables = soup.find_all("table")

            for table in tables:

                table_specs = []

                rows = table.find_all("tr")

                for row in rows:

                    cols = [
                        c.get_text(" ", strip=True)
                        for c in row.find_all(["td", "th"])
                    ]
 
                    cols = [c for c in cols if c]

                    if len(cols) < 2:
                        continue

                    for i in range(0, len(cols) - 1, 2):

                        label = cols[i]
                        value = cols[i + 1]

                        if not label or not value:
                            continue
   
                        table_specs.append((label, value))

                if is_valid_spec_table(table_specs):
                    generic_specs.extend(table_specs)

        print(f"[GENERIC HTML SPECS] {len(generic_specs)}")
        print(generic_specs[:15])

        markdown = soup.get_text("\n", strip=True)
    
        result = type("obj", (), {
            "success": True,
            "status_code": 200,
            "url": URL,
            "html": html,
            "markdown": None
        })()

    else:
        print("\n[STANDARD CRAWL4AI MODE]")

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=URL, config=run_config)

        if not result or not result.success:
            print("\n===== ERROR =====")
            print(result.error_message if result else "No result returned")
            return

        html = result.html or ""
        soup = BeautifulSoup(html, "lxml")

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

    if next_specs or extracted_specs:
        skip_generic_html = True
        print("[STRUCTURED SPECS FOUND - SKIPPING GENERIC HTML]")

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
    if result:
        print("Success:", result.success)
        print("Status Code:", result.status_code)
        print("Final URL:", result.url)
    else:
        print("Success: True (manual fetch)")
        print("Status Code: 200")
        print("Final URL:", URL)

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

    if product and product.get("additionalProperty"):
        print("[SKIPPING GENERIC HTML SPECS - JSON-LD additionalProperty present]")
        combined_specs = extracted_specs + next_specs
    else:
        combined_specs = extracted_specs + next_specs + generic_specs

    hard_ids = extract_hard_ids(html if html else markdown)

    for k, v in hard_ids:
        combined_specs.append((k, v))

    html_upc = get_upc(html)
    if html_upc:
        combined_specs.append(("gtin", html_upc))

    labeled_ids = extract_labeled_ids(markdown)

    if not gtin and labeled_ids["gtin"]:
        gtin = labeled_ids["gtin"]
        print(f"[LABEL GTIN FOUND] {gtin}")

    if not model and labeled_ids["model"]:
        model = labeled_ids["model"]
        print(f"[LABEL MODEL FOUND] {model}")

    if not model:
        fallback_model = extract_model_fallback(markdown)
        if fallback_model:
            model = fallback_model
            print(f"[FALLBACK MODEL FOUND] {model}")

    identity = {
        "gtin": gtin,
        "model": model,
        "sku": sku,
        "dpci": None
    }

    clean_specs = []

    for name, value in combined_specs:
        k = str(name).lower()
        val = str(value).strip()

        if k in ["gtin", "upc"]:
            if val.isdigit() and 12 <= len(val) <= 14:
                identity["gtin"] = val
                print(f"[IDENTITY] GTIN: {val}")
            else:
                print(f"[REJECTED GTIN] {val}")
            continue

        elif k in ["model_number", "mpn"]:
            identity["model"] = val
            print(f"[IDENTITY] MODEL_NUMBER (PRIORITY): {val}")
            continue
 
        elif k == "model":
            if not identity["model"]:
                identity["model"] = val
                print(f"[IDENTITY] MODEL (FALLBACK): {val}")
            continue

        elif k == "sku":
            identity["sku"] = val
            print(f"[IDENTITY] SKU: {val}")
            continue

        elif k == "dpci":
            identity["dpci"] = val
            print(f"[IDENTITY] DPCI: {val}")
            continue

        clean_specs.append((name, value))

    combined_specs = [
        {
            "source_label": name,
            "source_value": value
        }
        for name, value in clean_specs
    ]

    if product and product.get("additionalProperty"):
        for p in product["additionalProperty"]:
            if not isinstance(p, dict):
                continue

            name = p.get("name")
            value = p.get("value")
  
            if name and value:
                combined_specs.append({
                    "source_label": name,
                    "source_value": value
                })

    print("\n=== DEBUG: BEFORE process_product ===")
    print("combined_specs len:", len(combined_specs))
    print("markdown len:", len(markdown) if markdown else 0)
    print("product exists:", bool(product))

    structured_input = None

    if extracted_specs or next_specs:
        structured_input = combined_specs

    structured = process_product(
        product_json=product,
        markdown=markdown,
        category=CATEGORY,
        structured_input=structured_input
    )
    structured = list(structured or [])

    llm_gtin = None
    llm_model = None

    for attr, data in structured:
        val = data.get("display") if isinstance(data, dict) else str(data)
        val = str(val).strip()

        if attr == "gtin" and val.isdigit() and 12 <= len(val) <= 14:
            llm_gtin = val
  
        elif attr == "model" and val:
            llm_model = val

    if llm_gtin:
        identity["gtin"] = llm_gtin
        print(f"[LLM OVERRIDE GTIN] {llm_gtin}")

    if llm_model:
        identity["model"] = llm_model
        print(f"[LLM OVERRIDE MODEL] {llm_model}")

    filtered = []

    for attr, data in structured:
        if is_identity(attr, data):
            print(f"[POST-FILTER IDENTITY REMOVED] {attr}: {data}")
            continue
        filtered.append((attr, data))

    structured = filtered

    print("\n=== DEBUG: AFTER process_product ===")
    print("structured len:", len(structured))
    print("structured sample:", structured[:5])

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

    if identity["gtin"]:
        product_id = identity["gtin"]
    elif identity["model"]:
        product_id = identity["model"]
    elif identity["sku"]:
        product_id = identity["sku"]
    else:
        product_id = URL
  
    if product is None:
        product = {}

    product["model"] = identity["model"] or product_id
    product["gtin"] = identity["gtin"]
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

    if not product.get("gtin"):
        product["gtin"] = identity["gtin"]

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

        if display and str(display).lower() in ["not specified", "n/a", "unknown", ""]:
            continue

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