import requests
import xml.etree.ElementTree as ET


def parse_sitemap(url):

    urls = []

    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[SITEMAP ERROR] {url} -> {e}")
        return urls

    try:
        root = ET.fromstring(r.text)
    except Exception:
        print(f"[SITEMAP XML ERROR] {url}")
        return urls

    tag = root.tag.lower()

    # --------------------------------------------------
    # CASE 1: SITEMAP INDEX
    # --------------------------------------------------

    if "sitemapindex" in tag:

        for elem in root.iter():

            if elem.tag.lower().endswith("loc"):

                child_url = elem.text.strip()

                if child_url.endswith(".xml"):
                    urls.extend(parse_sitemap(child_url))

        return urls

    # --------------------------------------------------
    # CASE 2: URLSET
    # --------------------------------------------------

    if "urlset" in tag:

        for elem in root.iter():

            if elem.tag.lower().endswith("loc"):

                loc = elem.text.strip()

                if loc.startswith("http"):
                    urls.append(loc)

    return urls