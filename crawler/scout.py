import asyncio
import json
import re
import random
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from crawl4ai import AsyncWebCrawler, BrowserConfig

from config import SEED_URLS, RETAILER_CONFIG, PRODUCT_URL_PATTERNS, BROWSER_CONFIG, HIGH_SECURITY_DOMAINS
from db import get_db, save_url, count_urls
from search_bridge import get_crawl_priority


async def fetch_with_cdp(url):
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        for _ in range(20):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)

        return await page.content()


async def get_page(url, retries=2):
    for i in range(retries):
        try:
            return await fetch_with_cdp(url)
        except Exception:
            if i == retries - 1:
                return None
            await asyncio.sleep(3)


async def crawl_page(url):
    async with AsyncWebCrawler(config=BrowserConfig(**BROWSER_CONFIG)) as crawler:
        result = await crawler.arun(url=url)

        if not result or not result.html:
            return None

        html = result.html

        if hasattr(result, "page") and result.page:
            page = result.page
            for _ in range(20):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
            html = await page.content()

        return html


def retailer_config(url):
    domain = urlparse(url).netloc.lower()
    for key in RETAILER_CONFIG:
        if key in domain:
            return RETAILER_CONFIG[key]
    return None


def product_key(url: str) -> str:
    url = url.lower().split("?")[0].split("#")[0]

    sku_match = re.search(r"/sku/(\d+)", url)
    if sku_match:
        return f"sku_{sku_match.group(1)}"

    id_match = re.search(r"/([a-z0-9]{8,})/?$", url)
    if id_match:
        return id_match.group(1)

    return url


async def run_scout():
    conn = get_db()
    print("SCOUT STARTED")

    global_visited_pages = set()

    for category, seed_urls in SEED_URLS.items():
        existing = count_urls(conn, category)

        if existing >= 50:
            print(f"Skipping {category} ({existing})")
            continue

        print(f"Category: {category}")
        total_collected = set()
        target_per_seed = max(1, 50 // len(seed_urls))

        for seed_url in seed_urls:
            seed_collected = 0
            before_count = len(total_collected)

            if len(total_collected) >= 50:
                break

            if seed_url in global_visited_pages:
                continue

            print(f"Processing Seed: {seed_url}")
            seed_brand = None

            match = re.search(r'brand_facet=Brand%7E([^&]+)', seed_url)
            if match:
                seed_brand = match.group(1).lower()
            else:
                parts = seed_url.lower().split("/")
                for part in parts:
                    if "-" in part and not part.startswith("n-"):
                        seed_brand = part.replace("-", " ")
                        break
            
            print(f"[SEED BRAND]: {seed_brand}")
            print(f"[TARGET PER SEED]: {target_per_seed}")

            config = retailer_config(seed_url)
            if not config:
                continue

            next_selector = config.get("next_selector")
            visited_pages = global_visited_pages
            queue = [seed_url]

            while queue and seed_collected < target_per_seed and len(total_collected) < 50:
                current_url = queue.pop(0)

                if current_url in visited_pages:
                    continue

                visited_pages.add(current_url)

                html = await crawl_page(current_url) if is_high_security(current_url) else await fetch_with_crawler(current_url)

                if not html:
                    continue

                found_links = set()

                patterns = [
                    r'productBySkuId":\s*({.*?})',
                    r'__REHYDRATE_STATE__\s*=\s*({.*?});',
                    r'__NEXT_DATA__\s*=\s*({.*?});',
                    r'__PRELOADED_STATE__\s*=\s*({.*?});'
                ]

                for pattern in patterns:
                    match = re.search(pattern, html)
                    if match:
                        try:
                            data = json.loads(match.group(1))
                            json_str = json.dumps(data)
                            potential_paths = re.findall(r'"((?:/site/|/p/|/ip/|/dp/)[^"]+)"', json_str)
                            for path in set(potential_paths):
                                full_url = urljoin(current_url, path)

                                if not is_likely_product_url(full_url):
                                    continue

                                if seed_brand not in full_url.lower():
                                    continue

                                found_links.add(full_url)
                        except:
                            continue

                print("grid links:", len(found_links))

                if len(found_links) == 0:
                    soup = BeautifulSoup(html, "lxml")
                    config = retailer_config(current_url)
                    selectors = config.get("container_selectors", []) if config else []

                    for selector in selectors:
                        for el in soup.select(selector):
                            text = el.get_text(" ", strip=True).lower()

                            if seed_brand not in text:
                                continue

                            href = el.get("href")
                            if not href:
                                continue

                            href = urljoin(current_url, href)
 
                            if is_likely_product_url(href):
                                found_links.add(href)

                    if found_links:
                        print("selector links:", len(found_links))

                if 0 < len(found_links) < 20:
                    print("continuing pagination")

                if len(found_links) == 0:
                    continue

                for href in found_links:
                    if seed_collected >= target_per_seed:
                        break

                    key = product_key(href)

                    if key in total_collected:
                        continue

                    row = conn.execute(
                        "SELECT COUNT(*) as c FROM pending_crawl WHERE category=?",
                        (category,)
                    ).fetchone()

                    if row and row["c"] >= 50:
                        break

                    total_collected.add(key)
                    seed_collected += 1

                    priority = get_crawl_priority(conn, href)
                    save_url(conn, href, category, priority=priority, status="discovered")

                    print(f"SAVED: {href}")

                if len(total_collected) < 50 and next_selector:
                    soup = BeautifulSoup(html, "lxml")
                    next_el = soup.select_one(next_selector)

                    if next_el:
                        href = next_el.get("href")
                        if href:
                            href = urljoin(current_url, href)
                            if href not in visited_pages:
                                queue.append(href)
                                print(f"Queued next page: {href}")

                conn.commit()
                await asyncio.sleep(random.uniform(10, 25))

            if len(total_collected) == before_count:
                print(f"Seed exhausted: {seed_url}")

    conn.close()
    print("SCOUT FINISHED")


if __name__ == "__main__":
    asyncio.run(run_scout())
