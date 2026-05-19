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

                next_specs = get_target_specs_direct(url)

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

                    await page.evaluate(
                        "window.scrollTo(0, document.body.scrollHeight)"
                    )

                    await page.wait_for_timeout(5000)

                    html = await page.content()

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

                skip_generic_html = bool(
                    next_specs or extracted_specs
                )

                if skip_generic_html:
                    print(
                        "[STRUCTURED SPECS FOUND - "
                        "SKIPPING GENERIC HTML]"
                    )

                generic_specs = []

                if not skip_generic_html:
                    generic_specs = (
                        extract_generic_html_specs(html)
                    )

                print(
                    f"[GENERIC HTML SPECS] "
                    f"{len(generic_specs)}"
                )

                print(generic_specs[:15])

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

    else:

        if "target.com" in domain:

            print("\n[USING TARGET REDSKY API]")

            next_specs = get_target_specs_direct(url)

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

            skip_generic_html = bool(
                next_specs or extracted_specs
            )

            if skip_generic_html:
                print(
                    "[STRUCTURED SPECS FOUND - "
                    "SKIPPING GENERIC HTML]"
                )

            generic_specs = []

            if not skip_generic_html:
                generic_specs = (
                    extract_generic_html_specs(html)
                )

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