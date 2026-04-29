from bs4 import BeautifulSoup

def extract_spec_sheet_url(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True).lower()
        if "spec" in text and "sheet" in text:
            href = a["href"]
            if href.lower().endswith(".pdf"):
                return href

    return None