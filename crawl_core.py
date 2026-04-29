from __future__ import annotations
import gzip, hashlib, os, time
from dataclasses import dataclass
from typing import Optional
import requests
from playwright.sync_api import sync_playwright

@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str
    sha256: str
    path: str

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()

def save_gz_text(text: str, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(text)

def fetch_html(url: str, user_agent: str, timeout_s: int) -> FetchResult:
    r = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout_s)
    r.raise_for_status()
    html = r.text
    h = sha256_text(html)
    return FetchResult(url=url, status_code=r.status_code, html=html, sha256=h, path="")

def fetch_rendered_html(url: str, user_agent: str, timeout_s: int) -> str:
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            user_agent=user_agent
        )

        page.goto(url, wait_until="networkidle", timeout=timeout_s * 1000)

        try:
            page.locator("text=Specs").click(timeout=2000)
        except:
            pass

        html = page.content()

        browser.close()

        return html