import asyncio
import json
import requests

from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    CacheMode,
    BrowserConfig
)

from config import (
    HIGH_SECURITY_DOMAINS,
    HEAVY_JS_DOMAINS,
    INTERACTIVE_DOMAINS
)

from extraction.target import (
    find_specs,
    extract_target_specs,
    get_upc,
    get_target_specs_direct
)

from extraction.walmart import (
    extract_walmart_specs
)

from extraction.generic_html import (
    extract_generic_html_specs
)

from identity.gtin import (
    normalize_gtin
)


def normalize_domain(url):
    domain = urlparse(url).netloc.lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


async def fetch_page(url):

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
            text.includes("processor") &&
            text.includes("memory") &&
            text.includes("storage");

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

    HEAVY_JS_SCRIPT = """
    (async () => {
        await new Promise(r => setTimeout(r, 6000));
        window.scrollTo(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 4000));
    })();
    """

    DEFAULT_JS = """
    (async () => {
        await new Promise(r => setTimeout(r, 4000));
        window.scrollTo(0, document.body.scrollHeight);
        await new Promise(r => setTimeout(r, 4000));
    })();
    """

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

                browser = await p.chromium.connect_over_cdp(
                    "http://localhost:9222"
                )

                context = browser.contexts[0]
                page = (
                    context.pages[0]
                    if context.pages
                    else await context.new_page()
                )

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

                page.on(
                    "response",
                    lambda response: asyncio.create_task(
                        handle_response(response)
                    )
                )

                await page.goto(url)

                await page.wait_for_load_state(
                    "domcontentloaded"
                )

                try:
                    await page.wait_for_load_state(
                        "networkidle"
                    )
                except:
                    pass

                await page.wait_for_timeout(3000)
                await page.wait_for_timeout(8000)

                html = await page.content()

            soup = BeautifulSoup(html, "lxml")
            markdown = soup.get_text("\n", strip=True)

            result = type(
                "obj",
                (),
                {
                    "success": True,
                    "status_code": 200,
                    "url": url,
                    "html": html,
                    "markdown": None
                }
            )()

        elif is_jbl:

            async with async_playwright() as p:

                browser = await p.chromium.connect_over_cdp(
                    "http://localhost:9222"
                )

                context = browser.contexts[0]
                page = (
                    context.pages[0]
                    if context.pages
                    else await context.new_page()
                )

                jbl_payloads = []

                async def handle_response(response):
                    try:
                        response_url = response.url.lower()

                        if any(
                            k in response_url
                            for k in ["product", "products", "dw", "api"]
                        ):
                            data = await response.json()

                            if isinstance(data, dict):
                                jbl_payloads.append(data)
                                print("[JBL PAYLOAD]", response_url)

                    except:
                        pass

                page.on(
                    "response",
                    lambda r: asyncio.create_task(
                        handle_response(r)
                    )
                )

                await page.goto(url)

                await page.wait_for_load_state(
                    "domcontentloaded"
                )

                try:
                    await page.wait_for_load_state(
                        "networkidle"
                    )
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
                                next_specs.append(
                                    (name, value)
                                )

                    except:
                        pass

            print("\n[JBL SPECS COUNT]:", len(next_specs))

            if next_specs:
                print("[JBL SAMPLE]:", next_specs[:5])

            result = type(
                "obj",
                (),
                {
                    "success": True,
                    "status_code": 200,
                    "url": url,
                    "html": html,
                    "markdown": None
                }
            )()

        else:

            if "target.com" in domain:

                print("\n[USING TARGET REDSKY API]")

                target_data = get_target_specs_direct(url)

                next_specs = target_data.get("specifications", [])

                extracted_specs.append(
                    ("title", target_data.get("title"))
                )

                extracted_specs.append(
                    ("brand", target_data.get("brand"))
                )

                extracted_specs.append(
                    ("price", target_data.get("price"))
                )

                extracted_specs.append(
                    ("image_url", target_data.get("image_url"))
                )

                extracted_specs.append(
                    ("model", target_data.get("model"))
                )

                print(
                    "\n[TARGET SPECS COUNT]:",
                    len(next_specs)
                )

                headers = {
                    "User-Agent":
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36",

                    "Accept": "text/html",
                    "Referer": "https://www.target.com/"
                }

                try:
                    html_resp = requests.get(
                        url,
                        headers=headers,
                        timeout=20
                    )

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
                        next_specs.append(
                            ("gtin", html_upc)
                        )

                        print(
                            f"[TARGET HTML GTIN APPENDED]: "
                            f"{html_upc}"
                        )

                result = type(
                    "obj",
                    (),
                    {
                        "success": True,
                        "status_code": 200,
                        "url": url,
                        "html": html,
                        "markdown": None
                    }
                )()

            else:

                async with async_playwright() as p:

                    browser = await p.chromium.connect_over_cdp(
                        "http://localhost:9222"
                    )

                    context = browser.contexts[0]

                    page = (
                        context.pages[0]
                        if context.pages
                        else await context.new_page()
                    )

                    await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=90000
                    )

                    await page.wait_for_load_state(
                        "domcontentloaded"
                    )

                    if is_interactive:

                        print("\n[EXPANDING ACCORDIONS]")

                        try:
                            await page.wait_for_load_state(
                                "networkidle"
                            )
                        except:
                            pass

                        await page.wait_for_timeout(3000)

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

                        if count > 0:

                            try:

                                spec = page.locator(spec_selector).first

                                text = await spec.inner_text()

                                print("[CLICK TARGET]", text[:120])

                                button = spec.locator(
                                    "xpath=ancestor::*[@role='button' or self::button or self::summary][1]"
                                )

                                if await button.count() == 0:
                                    button = spec

                                await button.scroll_into_view_if_needed()

                                await page.wait_for_timeout(1000)

                                await button.click(force=True)

                                print("[SPEC CLICKED]")
        
                                await page.wait_for_timeout(2500)

                                for _ in range(6):

                                    try:

                                        buttons = page.locator(
                                            "text=/see more|show more|expand|view more/i"
                                        )

                                        expand_count = await buttons.count()

                                        for i in range(expand_count):
   
                                            btn = buttons.nth(i)

                                            try:
 
                                                if await btn.is_visible(): 

                                                    txt = await btn.inner_text()

                                                    print(f"[EXPAND CLICK] {txt[:80]}")

                                                    await btn.scroll_into_view_if_needed()

                                                    await page.wait_for_timeout(300)

                                                    await btn.click(force=True)

                                                    await page.wait_for_timeout(1200)

                                            except Exception as e:
                                                print("[EXPAND CLICK FAILED]", e)

                                    except Exception as e:
                                        print("[EXPAND LOOP ERROR]", e)

                            except Exception as e:
                                print("[SPEC CLICK ERROR]", e)

                        else:
                            print("[SPEC TEXT NOT FOUND]")

                        await page.wait_for_timeout(3000)

                    else:

                        await page.wait_for_timeout(1500)

                    html = ""
                    
                    for _ in range(3):

                        try:

                            await page.wait_for_load_state(
                                "networkidle"
                            )

                        except:
                            pass

                        await page.wait_for_timeout(2000)

                        try:

                            html = await page.content()
                            break

                        except Exception as e:

                            print("[CONTENT RETRY]", e)

                            await page.wait_for_timeout(1000)

                soup = BeautifulSoup(html, "lxml")

                try:

                    if "walmart.com" in domain:

                        next_data_tag = soup.find(
                            "script",
                            id="__NEXT_DATA__"
                        )

                        if next_data_tag:

                            print("\n[WALMART DETECTED - CDP]")

                            data = json.loads(
                                next_data_tag.string
                            )

                            next_specs = extract_walmart_specs(data)

                            print(
                                "\n[WALMART SPECS COUNT]:",
                                len(next_specs)
                            )

                            if next_specs:
                                print(
                                    "[SAMPLE]:",
                                    next_specs[:3]
                                )

                except:
                    pass

                markdown = soup.get_text("\n", strip=True)

                skip_generic_html = bool(next_specs)

                if skip_generic_html:
                    print(
                        "[STRUCTURED SPECS FOUND - "
                        "SKIPPING GENERIC HTML]"
                    )

                if not skip_generic_html:
                    print("[CALLING GENERIC HTML EXTRACTION]")
                    generic_specs = extract_generic_html_specs(html)
                else:
                    generic_specs = []

                print(
                    f"[GENERIC HTML SPECS] "
                    f"{len(generic_specs)}"
                )

                print(generic_specs[:15])

                result = type(
                    "obj",
                    (),
                    {
                        "success": True,
                        "status_code": 200,
                        "url": url,
                        "html": html,
                        "markdown": None
                    }
                )()

    else:

        if "target.com" in domain:

            print("\n[USING TARGET REDSKY API]")

            target_data = get_target_specs_direct(url)

            next_specs = target_data.get("specifications", [])

            extracted_specs.append(
                ("title", target_data.get("title"))
            )

            extracted_specs.append(
                ("brand", target_data.get("brand"))
            )

            extracted_specs.append(
                ("price", target_data.get("price"))
            )

            extracted_specs.append(
                ("image_url", target_data.get("image_url"))
            )

            extracted_specs.append(
                ("model", target_data.get("model"))
            )

            print(
                "\n[TARGET SPECS COUNT]:",
                len(next_specs)
            )

            headers = {
                "User-Agent":
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",

                "Accept": "text/html",
                "Referer": "https://www.target.com/"
            }

            try:
                html_resp = requests.get(
                    url,
                    headers=headers,
                    timeout=20
                )

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
                    next_specs.append(
                        ("gtin", html_upc)
                    )

                    print(
                        f"[TARGET HTML GTIN APPENDED]: "
                        f"{html_upc}"
                    )

            result = type(
                "obj",
                (),
                {
                    "success": True,
                    "status_code": 200,
                    "url": url,
                    "html": html,
                    "markdown": None
                }
            )()

        else:

            async with AsyncWebCrawler(
                config=browser_config
            ) as crawler:

                result = await crawler.arun(
                    url=url,
                    config=run_config
                )

            html = result.html or ""

            soup = BeautifulSoup(html, "lxml")

            try:

                if "walmart.com" in domain:

                    next_data_tag = soup.find(
                        "script",
                        id="__NEXT_DATA__"
                    )

                    if next_data_tag:

                        print("\n[WALMART DETECTED - STANDARD]")

                        data = json.loads(
                            next_data_tag.string
                        )

                        next_specs = extract_walmart_specs(data)

                        print(
                            "\n[WALMART SPECS COUNT]:",
                            len(next_specs)
                        )

                        if next_specs:
                            print(
                                "[SAMPLE]:",
                                next_specs[:3]
                            )

            except:
                pass

            markdown = soup.get_text(
                "\n",
                strip=True
            ) 

            skip_generic_html = bool(next_specs)

            if skip_generic_html:
                print(
                    "[STRUCTURED SPECS FOUND - "
                    "SKIPPING GENERIC HTML]"
                )

            if not skip_generic_html:
                print("[CALLING GENERIC HTML EXTRACTION]")
                generic_specs = extract_generic_html_specs(html)
            else:
                generic_specs = []

            print(
                f"[GENERIC HTML SPECS] "
                f"{len(generic_specs)}"
            )

            print(generic_specs[:15])

            if (
                result.markdown
                and getattr(
                    result.markdown,
                    "raw_markdown",
                    None
                )
            ):
                markdown = result.markdown.raw_markdown

            elif (
                result.markdown
                and getattr(
                    result.markdown,
                    "fit_markdown",
                    None
                )
            ):
                markdown = result.markdown.fit_markdown

            else:
                markdown = soup.get_text(
                    "\n",
                    strip=True
                )

    return {
        "html": html,
        "markdown": markdown,
        "next_specs": next_specs,
        "generic_specs": generic_specs,
        "extracted_specs": extracted_specs,
        "spec_payloads": spec_payloads,
        "result": result,
        "domain": domain
    }