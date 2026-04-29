from __future__ import annotations
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


def extract_links(base_url: str, html: str) -> list[str]:

    soup = BeautifulSoup(html, "html.parser")

    base_domain = urlparse(base_url).netloc

    links = []
    seen = set()

    for a in soup.select("a[href]"):

        href = a.get("href")

        if not href:
            continue

        abs_url = urljoin(base_url, href)

        parsed = urlparse(abs_url)

        # Only crawl http/https
        if parsed.scheme not in ("http", "https"):
            continue

        # Stay within the same domain
        if parsed.netloc != base_domain:
            continue

        # Remove fragments (#reviews, #specs, etc.)
        abs_url = abs_url.split("#")[0]

        # Remove query parameters (?sort=price etc.)
        abs_url = abs_url.split("?")[0]

        if abs_url not in seen:
            seen.add(abs_url)
            links.append(abs_url)

    return links