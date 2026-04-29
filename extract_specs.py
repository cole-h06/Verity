from bs4 import BeautifulSoup
import re
import json
from urllib.parse import urlparse


MODEL_REGEX = re.compile(r"\b[A-Z]{1,5}[-]?[A-Z0-9]*\d+[A-Z0-9\-]*\b")
BARCODE_REGEX = re.compile(r"\b\d{12,14}\b")


# --------------------------------------------------
# PRODUCT IDENTITY VERIFICATION
# --------------------------------------------------

def verify_product_identity(expected_brand, expected_model, page_text):

    if not page_text:
        return False

    text = page_text.lower()
    score = 0

    if expected_model and expected_model.lower() in text:
        score += 2

    if expected_brand and expected_brand.lower() in text:
        score += 1

    return score >= 2


SPEC_SECTION_HINTS = [
    "spec",
    "specification",
    "technical",
    "feature",
    "detail",
    "product-spec",
    "tech-spec",
    "key-feature",
    "product-detail",
    "product-info",
    "attribute",
]

BARCODE_KEYS = [
    "upc",
    "ean",
    "gtin",
    "barcode",
]


# --------------------------------------------------
# SPEC VALIDATION
# --------------------------------------------------

def is_valid_spec(attr: str, val: str) -> bool:

    if not attr or not val:
        return False

    attr = attr.strip()
    val = val.strip()

    if not any(c.isalpha() for c in attr):
        return False

    if len(attr) > 60 or len(val) > 120:
        return False

    if len(attr.split()) > 6:
        return False

    if attr.lower() == val.lower():
        return False

    if "$" in val:
        return False

    if not any(c.isdigit() for c in val):
        return False

    return True


# --------------------------------------------------
# JSON WALKER
# --------------------------------------------------

def find_specs_in_json(obj):

    specs = []

    if isinstance(obj, dict):

        for k, v in obj.items():

            if isinstance(v, (str, int, float)):

                if is_valid_spec(str(k), str(v)):
                    specs.append((str(k), str(v)))

            elif isinstance(v, list) or isinstance(v, dict):
                specs.extend(find_specs_in_json(v))

    elif isinstance(obj, list):

        for item in obj:
            specs.extend(find_specs_in_json(item))

    return specs


# --------------------------------------------------
# JSON-LD EXTRACTION
# --------------------------------------------------

def extract_specs_from_jsonld(soup):

    rows = []

    scripts = soup.find_all("script", {"type": "application/ld+json"})

    for s in scripts:

        text = s.string or s.text

        if not text:
            continue

        try:
            data = json.loads(text)
        except:
            continue

        blocks = data if isinstance(data, list) else [data]

        for block in blocks:

            if not isinstance(block, dict):
                continue

            if "@graph" in block:
                blocks.extend(block["@graph"])

            if block.get("@type") == "Product":

                props = block.get("additionalProperty")

                if isinstance(props, list):

                    for p in props:

                        k = p.get("name")
                        v = p.get("value")

                        if k and v and is_valid_spec(str(k), str(v)):
                            rows.append((str(k), str(v)))

                rows.extend(find_specs_in_json(block))

    return rows


# --------------------------------------------------
# MODEL EXTRACTION FROM JSON-LD
# --------------------------------------------------

def extract_model_from_schema(soup):

    scripts = soup.find_all("script", {"type": "application/ld+json"})

    for s in scripts:

        text = s.string or s.text

        if not text:
            continue

        try:
            data = json.loads(text)
        except:
            continue

        blocks = data if isinstance(data, list) else [data]

        for block in blocks:

            if not isinstance(block, dict):
                continue

            if "@graph" in block:
                blocks.extend(block["@graph"])

            if block.get("@type") == "Product":

                for field in ["model", "mpn", "sku", "productID"]:
                    if field in block:
                        return str(block[field])

    return None


# --------------------------------------------------
# REACT / HYDRATION EXTRACTION
# --------------------------------------------------

def extract_react_specs(soup):

    specs = []

    scripts = soup.find_all("script")

    for script in scripts:

        text = script.string or script.text

        if not text:
            continue

        if "__NEXT_DATA__" in text or "__INITIAL_STATE__" in text or "product" in text.lower():

            start = text.find("{")

            if start == -1:
                continue

            json_blob = text[start:]

            try:
                data = json.loads(json_blob)
            except:
                continue

            specs.extend(find_specs_in_json(data))

    return specs


# --------------------------------------------------
# EMBEDDED JS OBJECT EXTRACTION
# --------------------------------------------------

def extract_specs_from_js(soup):

    specs = []

    scripts = soup.find_all("script")

    for script in scripts:

        text = script.string

        if not text:
            continue

        if "spec" not in text.lower():
            continue

        try:

            json_blocks = re.findall(r"\{.*?\}", text, re.DOTALL)

            for block in json_blocks:

                try:
                    data = json.loads(block)
                except:
                    continue

                specs.extend(find_specs_in_json(data))

        except:
            pass

    return specs


# --------------------------------------------------
# BRAND RESOLUTION
# --------------------------------------------------

def extract_brand_from_schema(soup):

    scripts = soup.find_all("script", {"type": "application/ld+json"})

    for s in scripts:

        text = s.string or s.text

        if not text:
            continue

        try:
            data = json.loads(text)
        except:
            continue

        if isinstance(data, dict):

            if "brand" in data:

                brand = data["brand"]

                if isinstance(brand, dict):
                    return brand.get("name")

                if isinstance(brand, str):
                    return brand

    return None


def extract_brand_meta(soup):

    meta = soup.find("meta", {"property": "product:brand"})

    if meta and meta.get("content"):
        return meta["content"]

    return None


def brand_from_domain(url):

    try:
        domain = urlparse(url).netloc.lower()
        parts = domain.split(".")

        if len(parts) >= 2:
            return parts[-2].upper()

    except:
        pass

    return None


def resolve_brand(soup, url):

    brand = extract_brand_from_schema(soup)

    if brand:
        return brand

    brand = extract_brand_meta(soup)

    if brand:
        return brand

    return brand_from_domain(url)


# --------------------------------------------------
# MODEL EXTRACTION
# --------------------------------------------------

def extract_model(text):

    if not text:
        return None

    m = MODEL_REGEX.search(text)

    if m:
        return m.group(0)

    return None


# --------------------------------------------------
# BARCODE DETECTION
# --------------------------------------------------

def detect_barcode(attr, val):

    attr_l = attr.lower()

    if any(k in attr_l for k in BARCODE_KEYS):

        digits = "".join(c for c in val if c.isdigit())

        if len(digits) in (12, 13, 14):
            return digits

    m = BARCODE_REGEX.search(val)

    if m:
        return m.group(0)

    return None


# --------------------------------------------------
# SECTION DETECTION
# --------------------------------------------------

def get_candidate_sections(soup):

    candidates = []

    for tag in soup.find_all(True):

        cls = " ".join(tag.get("class", []))
        id_ = tag.get("id", "")

        data = " ".join(f"{k}={v}" for k,v in tag.attrs.items())
        text = (cls + " " + id_ + " " + data).lower()

        if any(h in text for h in SPEC_SECTION_HINTS):
            candidates.append(tag)

    if not candidates:
        candidates = [soup]

    return candidates


# --------------------------------------------------
# MAIN EXTRACTION
# --------------------------------------------------

def extract_product_data(html, url=None, expected_brand=None, expected_model=None):

    soup = BeautifulSoup(html, "lxml")

    page_text = soup.get_text(" ", strip=True)

    if expected_model or expected_brand:

        if not verify_product_identity(expected_brand, expected_model, page_text):
            return None

    title = ""

    if soup.title:
        title = soup.title.get_text(strip=True)

    meta = soup.find("meta", {"property": "og:title"})
    if meta and meta.get("content"):
        title = meta["content"]

    brand = resolve_brand(soup, url)

    specs = []
    barcode = None
    model_from_specs = None
    model = None

    specs.extend(extract_specs_from_jsonld(soup))
    specs.extend(extract_specs_from_js(soup))
    specs.extend(extract_react_specs(soup))

    sections = get_candidate_sections(soup)

    for section in sections:

        for table in section.find_all("table"):

            for row in table.find_all("tr"):

                cols = row.find_all(["th", "td"])

                if len(cols) >= 2:

                    k = cols[0].get_text(strip=True)
                    v = cols[1].get_text(strip=True)

                    if not barcode:
                        bc = detect_barcode(k, v)
                        if bc:
                            barcode = bc

                    if is_valid_spec(k, v):
                        specs.append((k, v))

                        if not model_from_specs and any(x in k.lower() for x in ["model", "model number", "mpn", "sku"]):
                            m = extract_model(v)
                            if m:
                                model_from_specs = m

    schema_model = extract_model_from_schema(soup)

    if schema_model:
        model = schema_model
    elif model_from_specs:
        model = model_from_specs
    elif barcode:
        model = barcode
    else:
        candidate = extract_model(title)

        if candidate and any(c.isdigit() for c in candidate):
            model = candidate

    print(
        "[PRODUCT SIGNALS]",
        f"url={url}",
        f"schema_model={schema_model}",
        f"model_from_specs={model_from_specs}",
        f"title_model={extract_model(title)}",
        f"barcode={barcode}",
        f"spec_count={len(specs)}"
    )

    seen = set()
    clean = []

    for k, v in specs:

        key = (k.lower(), v.lower())

        if key not in seen:
            clean.append((k, v))
            seen.add(key)

    if not model and model_from_specs:
        model = model_from_specs

    is_product = bool(model or barcode or len(clean) >= 5)

    if not is_product:
        return None

    print(f"[SPEC EXTRACTION] {len(clean)} candidate specs")

    return {
        "brand": brand,
        "model": model,
        "title": title,
        "barcode": barcode,
        "specs": clean
    }