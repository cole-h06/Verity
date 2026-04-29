# crawler_parser.py

import sys
import os
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import html2text

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from llm_runtime import run_llm_v2
from db import resolve_canonical_model, get_db
from post_processing import process_and_store_claims

# ---------------------------------------------------------
# REGEX PATTERNS
# ---------------------------------------------------------

MODEL_REGEX = r"\b[A-Z]{1,5}[A-Z0-9\-]{3,}\d+[A-Z0-9\-]*\b"
UPC_REGEX = r"\b\d{12}\b"
EAN_REGEX = r"\b\d{13}\b"

def normalize_barcode(code):
    if not code:
        return None

    code = str(code).strip()

    code = re.sub(r"\D", "", code)

    if len(code) in (12, 13, 14):
        return code

    return None

# ---------------------------------------------------------
# EXTRACTION SCORING
# ---------------------------------------------------------

MEASUREMENT_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*[a-zA-Z°%]{1,5}\b",
    re.IGNORECASE
)

FRACTION_PATTERN = re.compile(
    r"\b\d+\s+\d+/\d+\b"
)

BINARY_PATTERN = re.compile(
    r"\b(yes|no|true|false|supported|not supported)\b",
    re.IGNORECASE
)

UNIT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*([a-zA-Z°%]+)"
)

def looks_like_measurement(value):

    v = str(value).lower().strip()

    if not any(c.isdigit() for c in v):
        return False

    if len(v.split()) <= 4:
        return True

    if any(sym in v for sym in ['"', "'", "x", "×", "/", "-", " by "]):
        return True

    return False

def split_value_unit(value):

    text = str(value).strip()

    tokens = re.findall(r"\d+(?:\.\d+)?\s*[a-zA-Z]+", text)

    if len(tokens) >= 2:
        values = []
        for t in tokens:
            m = UNIT_PATTERN.search(t)
            if m:
                values.append(m.group(1))
        return ", ".join(values), "mixed"

    match = UNIT_PATTERN.search(text)

    if not match:
        return value, None

    return match.group(1), match.group(2)

def passes_spec_gate(attr, value):

    attr_l = str(attr).lower().strip()
    val_l = str(value).lower().strip()

    if looks_like_measurement(val_l):
        return True

    if val_l in [
        "yes", "no",
        "true", "false",
        "supported", "not supported"
    ]:
        return True

    if any(k in attr_l for k in ["model", "sku", "part"]):
        if re.search(r"[A-Z0-9\-]{5,}", str(value)):
            return True

    if is_valid_claim(attr, value):
        return True

    return llm_spec_classifier(attr, value)

def structural_spec_score(value, attr=None):

    v = str(value).lower().strip()
    a = str(attr).lower().strip() if attr else ""

    if any(x in v for x in [
        "http://",
        "https://",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".gif"
    ]):
        return 0

    if any(x in a for x in [
        "alt_view",
        "zoom_",
        "thumbnail",
        "standard_",
        "image",
        "img"
    ]):
        return 0

    score = 0.0

    if MEASUREMENT_PATTERN.search(v):
        score += 0.7

    if FRACTION_PATTERN.search(v):
        score += 0.6

    if any(c.isdigit() for c in v):
        score += 0.2

    if len(v.split()) <= 4:
        score += 0.1

    return score

def llm_spec_classifier(attr, value):

    prompt = f"""
Is the following claim describing a PHYSICAL, TECHNICAL, or CHEMICAL property of a product?

Attribute: {attr}
Value: {value}

Examples of PHYSICAL properties:
width, height, voltage, wattage, capacity, screen size, refresh rate, weight, power, frequency

Examples of NON-PHYSICAL:
reviews, ratings, shipping, promotions, services,
image URLs, thumbnails, zoom levels, internal site variables

Answer ONLY:

YES
or
NO
"""

    result = run_llm_v2(
        system_prompt="Return ONLY YES or NO.",
        user_prompt=prompt,
        max_new_tokens=6
    )

    return "YES" in result.upper()

# ---------------------------------------------------------
# HTML to Visible Text
# ---------------------------------------------------------

def extract_visible_text(html: str):

    soup = BeautifulSoup(html, "lxml")

    for tag in soup([
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "svg",
        "noscript"
    ]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)

    return text

def extract_spec_container(soup):

    def is_anchor(tag):
        if tag.name not in {"h2", "h3", "h4"}:
            return False

        text = tag.get_text(" ", strip=True).lower()

        return bool(re.search(r"(spec|specification)", text))

    anchor = soup.find(is_anchor)

    if not anchor:
        return None, None

    for sibling in anchor.find_next_siblings():

        if sibling.name in {"h1", "h2", "h3"}:
            break

        if sibling.name in {"ul", "ol", "table", "dl"}:
            rows = sibling.find_all(["li", "tr", "dt", "dd"])
            if len(rows) >= 2:
                html = str(sibling)
                return (
                    BeautifulSoup(html, "html.parser").get_text("\n", strip=True),
                    html
                )

        if sibling.name == "div":

            inner = sibling.find(["ul", "ol", "table", "dl"])

            if inner:
                rows = inner.find_all(["li", "tr", "dt", "dd"])
                if len(rows) >= 2:
                    html = str(sibling)
                    return (
                        BeautifulSoup(html, "html.parser").get_text("\n", strip=True),
                        html
                    )

    return None, None

    def is_structured_block(tag):

        if tag.name in {"ul", "ol", "table", "dl"}:
            return len(tag.find_all(["li", "tr", "dd", "dt"])) >= 2

        if tag.name == "div":

            if tag.find(["ul", "ol", "table", "dl"]):
                return True

            text = tag.get_text("\n", strip=True)

            if not text or len(text) > 500:
                return False

            lines = [line.strip() for line in text.split("\n") if line.strip()]

            kv_pattern = 0

            for line in lines:
                if ":" in line or any(c.isdigit() for c in line):
                    kv_pattern += 1

            return kv_pattern >= 2

        return False

    anchor = soup.find(is_spec_header)

    if not anchor:
        return None, None

    blocks = []

    for sibling in anchor.find_next_siblings():

        if sibling.name in {anchor.name, "h1", "h2"}:
            break

        if is_structured_block(sibling):
            blocks.append(str(sibling))

    if not blocks:
        return None, None

    html = "".join(blocks)

    return (
        BeautifulSoup(html, "html.parser").get_text(separator="\n", strip=True),
        html
    )

# ---------------------------------------------------------
# PRODUCT METADATA EXTRACTION
# ---------------------------------------------------------

def extract_product_metadata(html, soup):

    brand = None
    model = None
    barcode = None
    title = None
    additional_specs = []
    barcodes = set()

    print("\n==============================")
    print("METADATA EXTRACTION")
    print("==============================")

    # -----------------------------
    # JSON-LD
    # -----------------------------

    scripts = soup.find_all("script", type="application/ld+json")

    for s in scripts:

        try:

            data = json.loads(s.string or "{}")

            if isinstance(data, list):
                data = data[0]

            if not isinstance(data, dict):
               continue

            type_val = data.get("@type")

            if isinstance(type_val, list):
                if "Product" not in type_val:
                    continue
            else:
                if type_val not in ("Product", "ProductGroup"):
                    continue

            title = data.get("name")

            model = data.get("model") or data.get("mpn") or data.get("sku")

            text = soup.get_text(" ", strip=True)

            for match in re.findall(UPC_REGEX, text):
                norm = normalize_barcode(match)
                if norm:
                    barcodes.add(norm)

            for match in re.findall(EAN_REGEX, text):
                norm = normalize_barcode(match)
                if norm:
                    barcodes.add(norm)

            brand_obj = data.get("brand")

            if isinstance(brand_obj, dict):
                brand = brand_obj.get("name")
            elif isinstance(brand_obj, str):
                brand = brand_obj

            additional_specs = []

            additional = data.get("additionalProperty", [])

            if isinstance(additional, list):

                for prop in additional:

                    name = prop.get("name")
                    value = prop.get("value")

                    if not name or not value:
                        continue
 
                    print(f"[JSON-LD ADDITIONAL PROPERTY] {name} = {value}")

                    additional_specs.append((name, value))

        except Exception as e:

            print("[JSON-LD PARSE ERROR]", e)

    # -----------------------------
    # META TITLE
    # -----------------------------

    if not title:

        meta = soup.find("meta", property="og:title")

        if meta and meta.get("content"):
            title = meta["content"]

    # -----------------------------
    # MODEL REGEX SCAN
    # -----------------------------

    if not model:

        text = soup.get_text(" ", strip=True)

        candidates = re.findall(MODEL_REGEX, text)

        for c in candidates:

            if len(c) >= 6 and any(x.isdigit() for x in c):

                model = c
                break

    # -----------------------------
    # BARCODE REGEX
    # -----------------------------

    if not barcode:

        text = soup.get_text(" ", strip=True)

        upc = re.search(UPC_REGEX, text)

        if upc:
            barcode = upc.group()

        else:

            ean = re.search(EAN_REGEX, text)

            if ean:
                barcode = ean.group()

    barcode = None

    if barcodes:
        barcode = list(barcodes)[0]

    print("\n----------- METADATA FOUND -----------")
    print("Title:", title)
    print("Brand:", brand)
    print("Model:", model)
    print("Barcode:", barcode)
    print("All barcodes found:", barcodes)
    print("--------------------------------------\n")

    return {
        "title": title,
        "brand": brand,
        "model": model,
        "barcode": barcode,
        "jsonld_specs": additional_specs
    }

# ---------------------------------------------------------
# SAFE JSON PARSE
# ---------------------------------------------------------

def safe_json_parse(text: str):
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except:
        pass

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        print("[JSON PARSE] No valid JSON boundaries")
        return None

    candidate = text[start:end+1]

    try:
        return json.loads(candidate)
    except Exception as e:
        print("[JSON PARSE ERROR]", e)
        return None

# ---------------------------------------------------------
# LLM RUNTIME
# ---------------------------------------------------------

def run_llm(prompt: str):

    print("\n==============================")
    print("Sending prompt to OpenVINO LLM")
    print("==============================")

    system_prompt = """
    You extract PRODUCT SPECIFICATIONS.

    A valid specification is a FIXED, INTRINSIC, PHYSICAL property of a product.

    STRICT RULES:

    - DO NOT extract ratings, scores, reviews, or evaluation metrics
    - If a value is a ratio or score, it is NOT a specification
    - A valid spec must exist independently of testing, users, or opinions
    - It must be a manufacturer-defined property
    - Prefer values with real-world units (inches, watts, volts, lbs)
    - Binary hardware features (yes/no) are allowed
    - Extract only explicit key-value specifications
    - Do not interpret or rewrite anything

    Output ONLY valid JSON.
    """

    output = run_llm_v2(
        system_prompt=system_prompt,
        user_prompt=prompt,
        max_new_tokens=800
    )

    print("\n----------- RAW LLM OUTPUT -----------")
    print(output)
    print("--------------------------------------")

    return output


# ---------------------------------------------------------
# CLAIM VALIDATION
# ---------------------------------------------------------

def is_valid_claim(attribute: str, value: str):

    if not attribute or not value:
        return False

    attr = str(attribute).strip()
    val = str(value).strip()

    # Attribute should be short label
    if len(attr.split()) > 5:
        return False

    if len(attr) > 60:
        return False

    # Value should be short categorical or numeric
    if len(val.split()) > 6:
        return False

    if len(val) > 60:
        return False

    # -------------------------------
    # 2. Must be atomic (not sentence)
    # -------------------------------

    if ":" in val:
        return False

    # Reject long prose-like values
    if len(val.split()) >= 6 and not re.search(r"\d", val):
        return False

    # -------------------------------
    # 3. Must have SOME signal
    # -------------------------------

    has_number = bool(re.search(r"\d", val))
    is_short_text = len(val.split()) <= 5

    if not (has_number or is_short_text):
        return False

    return True

def passes_structural_validation(attr: str, val: str, cluster_size: int):

    if not attr or not val:
        return False

    attr_l = str(attr).lower()
    val_l = str(val).lower()

    if attr_l in val_l and len(val_l) > len(attr_l) * 2:
        return False

    if cluster_size < 2:
        return False

    word_count = len(attr.split()) + len(val.split())
    if word_count > 12:
        return False

    if not any(c.isalpha() for c in attr):
        return False

    return True

# ---------------------------------------------------------
# SPEC ROW EXTRACTION
# ---------------------------------------------------------

def extract_spec_rows(soup):

    spec_keywords = [
        "specs",
        "specifications",
        "technical specifications",
        "tech specs"
    ]

    rows = []

    headings = soup.find_all(["h1","h2","h3","h4","h5","h6"])

    for h in headings:

        heading_text = h.get_text(" ", strip=True).lower()

        if not any(k in heading_text for k in spec_keywords):
            continue

        section = h.parent

        if not section:
            continue

        # ---------------- table specs ----------------

        for tr in section.find_all("tr"):

            cols = tr.find_all(["td","th"])

            if len(cols) >= 2:

                key = cols[0].get_text(" ", strip=True)
                val = cols[1].get_text(" ", strip=True)

                if key and val:
                    rows.append((key, val))

        # ---------------- dl specs ----------------

        for dl in section.find_all("dl"):

            dts = dl.find_all("dt")
            dds = dl.find_all("dd")

            for k,v in zip(dts,dds):

                key = k.get_text(" ", strip=True)
                val = v.get_text(" ", strip=True)

                if key and val:
                    rows.append((key,val))

        # ---------------- bullet specs ----------------

        for li in section.find_all("li"):

            text = li.get_text(" ", strip=True)

            if ":" in text:

                k,v = text.split(":",1)

                rows.append((k.strip(), v.strip()))

    if not rows:

        for div in soup.find_all(["div","p","span"]):

            text = div.get_text(" ", strip=True)

            if ":" in text:

                parts = text.split(":",1)

                if len(parts) == 2:

                    k = parts[0].strip()
                    v = parts[1].strip()

                    if k and v:

                        rows.append((k,v))

    return rows

def extract_text_specs(text):

    pairs = []

    pattern = re.findall(
        r"([A-Za-z\-\s\(\)\.]+?)\s+(Yes|No|\d+(?:\.\d+)?)",
        text
    )

    for attr, val in pattern:

        attr = attr.strip()
        val = val.strip()

        if not attr or not val:
            continue

        if len(attr.split()) > 8:
            continue

        pairs.append((attr, val))

    return pairs

# ---------------------------------------------------------
# SPEC SECTION DETECTION
# ---------------------------------------------------------

def has_specs_section(soup):

    keywords = [
        "specs",
        "specifications",
        "technical specifications",
        "tech specs"
    ]

    headings = soup.find_all(["h1","h2","h3","h4","h5","h6"])

    for h in headings:

        heading = h.get_text(" ", strip=True).lower()

        if not any(k in heading for k in keywords):
            continue

        parent = h.parent

        if not parent:
            continue

        if parent.find("table"):
            return True

        if parent.find("dl"):
            return True

        rows = parent.find_all(["tr","li","div","p"])

        spec_like = 0

        for r in rows:
 
            text = r.get_text(" ", strip=True)

            if ":" in text or re.search(r"\d", text):
                spec_like += 1

        if spec_like >= 3:
            return True

    return False

def is_structured_container(container_html):

    if not container_html:
        return False

    html = container_html.lower()

    return any(tag in html for tag in ["<table", "<dl", "<tr", "<li"])

# ---------------------------------------------------------
# TEXT CLAIM EXTRACTION (REVIEWS / BLOGS)
# ---------------------------------------------------------

def extract_claims_from_text(text, domain=None):

    print("\n[TEXT CLAIM EXTRACTION]")

    chunks = chunk_text(text, size=4000, overlap=500)

    all_claims = []

    domain_block = f"DOMAIN: {domain}\n\n" if domain else ""

    for chunk in chunks:

        if ":" not in chunk and "=" not in chunk:
            continue

        print("\n----------- TEXT CHUNK -----------")
        print(chunk[:500])
        print("----------------------------------")

        prompt = f"""
        {domain_block}
        Extract PRODUCT SPECIFICATIONS exactly as written.

        Return ONLY JSON:

        {{
          "claims": [
            {{"attribute": "...", "value": "...", "unit": "...", "source_text": "..."}}
          ]
        }}

        PAGE TEXT:
        {chunk}
        """

        response = run_llm(prompt)
        data = safe_json_parse(response)

        if not data:
            continue

        for c in data.get("claims", []):

            attr = c.get("attribute")
            val = c.get("value")

            if not is_valid_structural_spec(c, chunk):
                continue

            if not is_valid_claim(attr, val):
                continue

            all_claims.append({
                "attribute": attr,
                "value": val,
                "unit": c.get("unit")
            })

    print("[TEXT CLAIMS FOUND]", len(all_claims))

    return all_claims

def looks_atomic_value(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False

    if len(v.split()) > 4:
        return False

    if len(v) > 40:
        return False

    return True


def looks_atomic_key(key: str) -> bool:
    k = (key or "").strip()
    if not k:
        return False

    if len(k) > 60:
        return False

    if len(k.split()) > 8:
        return False

    return True

def split_kv_text(text: str):
    t = re.sub(r"\s+", " ", text).strip()
    if not t:
        return None, None

    if ":" in t:
        left, right = t.split(":", 1)
        return left.strip(), right.strip()

    if "=" in t:
        left, right = t.split("=", 1)
        return left.strip(), right.strip()

    return None, None

def is_valid_structural_spec(claim, raw_chunk):
    attr = re.sub(r"\s+", " ", claim.get("attribute", "")).strip()
    val = re.sub(r"\s+", " ", claim.get("value", "")).strip()
    src = re.sub(r"\s+", " ", claim.get("source_text", "")).strip()
    chunk = re.sub(r"\s+", " ", raw_chunk)

    if not attr or not val or not src:
        return False

    if src not in chunk:
        return False

    if not validate_markdown_alignment(claim, raw_chunk):
        return False

    if not re.search(r":|=", src):
        return False

    if len(src.split()) > 12:
        return False

    if len(attr.split()) > 6:
        return False

    if attr.lower() == val.lower():
        return False

    left_side, right_side = split_kv_text(src)

    if not left_side or not right_side:
        return False

    if not left_side or not right_side:
        return False

    if attr.lower() != left_side.lower():
        return False

    if val.lower() != right_side.lower():
        return False

    return True

def validate_markdown_alignment(claim, markdown_text):
    attr = re.sub(r"\s+", " ", claim.get("attribute", "")).strip().lower()
    val = re.sub(r"\s+", " ", claim.get("value", "")).strip().lower()

    if not attr or not val:
        return False

    lines = markdown_text.split("\n")

    for line in lines:
        line_clean = re.sub(r"\s+", " ", line).strip().lower()

        if ":" in line_clean:
            left, right = line_clean.split(":", 1)

            if attr == left.strip() and val == right.strip():
                return True

    return False

def extract_kv_from_row(row):
    tag = row.name.lower()

    if tag == "tr":
        cells = row.find_all(["th", "td"], recursive=False)
        if len(cells) >= 2:
            key = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            return key, value

    if tag == "dt":
        dd = row.find_next_sibling("dd")
        if dd:
            key = row.get_text(" ", strip=True)
            value = dd.get_text(" ", strip=True)
            return key, value

    text = row.get_text(" ", strip=True)
    return split_kv_text(text)


def score_spec_container(container):
    rows = container.find_all(["tr", "dt", "li"], recursive=False)

    if len(rows) < 4:
        return 0, []

    pairs = []
    atomic_pairs = 0
    numericish = 0
    booleanish = 0

    for row in rows:
        key, value = extract_kv_from_row(row)

        if not key or not value:
            continue

        if not looks_atomic_key(key):
            continue

        if not looks_atomic_value(value):
            continue

        pairs.append((key, value))
        atomic_pairs += 1

        low = value.lower().strip()
        if re.search(r"\d", value):
            numericish += 1
        elif low in {"yes", "no", "true", "false"}:
            booleanish += 1

    if atomic_pairs < 3:
        return 0, []

    ratio = (numericish + booleanish) / max(atomic_pairs, 1)

    score = atomic_pairs * 10 + int(ratio * 25)

    return score, pairs


def extract_specs_by_structure(soup):
    best_pairs = []
    best_score = 0

    candidates = soup.find_all(["table", "dl", "ul", "div"])

    for container in candidates:

        rows = container.find_all(["tr", "dt", "li", "div"], recursive=False)

        if len(rows) < 3:
            continue

        score, pairs = score_spec_container(container)

        if score > best_score:
            best_score = score
            best_pairs = pairs

    specs = []
    for key, value in best_pairs:
        specs.append((key, value))

    if specs:
        print(f"[STRUCTURAL CLUSTER FOUND] {len(specs)} specs (score={best_score})")

    return specs

def html_to_markdown(html: str) -> str:

    h = html2text.HTML2Text()

    h.ignore_links = True
    h.ignore_images = True
    h.ignore_emphasis = False

    h.body_width = 0

    markdown = h.handle(html)

    markdown = re.sub(r"\n{3,}", "\n\n", markdown)

    return markdown.strip()

def chunk_text(t, size=8000, overlap=1000):
    chunks = []
    start = 0
    n = len(t)

    while start < n:
        end = start + size
        chunk = t[start:end]
        chunks.append(chunk)
        start += size - overlap

    return chunks

# ---------------------------------------------------------
# MAIN PARSER
# ---------------------------------------------------------

def parse_page(html: str, url=None, rendered_specs=None, source_type="unknown", api_specs=None, conn=None):

    print("\n=================================================")
    print("Parsing new page")
    print("=================================================")

    soup = BeautifulSoup(html, "lxml")
    domain = urlparse(url).netloc if url else None

    if conn is None:
        conn = get_db()

    # -------------------------------------------------
    # METADATA EXTRACTION (CODE FIRST)
    # -------------------------------------------------

    metadata = extract_product_metadata(html, soup)

    brand = metadata["brand"]
    model = metadata["model"]
    barcode = metadata["barcode"]
    jsonld_specs = metadata.get("jsonld_specs", [])

    if model and brand:
        model = resolve_canonical_model(conn, model, brand)

    valid_specs = []

    if rendered_specs:

        cluster_size = len(rendered_specs)

        for spec in rendered_specs:

            attr = spec.get("attribute")
            val = spec.get("value")

            if not attr or not val:
                continue

            if not any(c.isalnum() for c in attr):
                continue

            if not passes_structural_validation(attr, val, cluster_size):
                continue

            if not passes_spec_gate(attr, val):
                continue

            if not is_valid_claim(attr, val):
                continue

            valid_specs.append(spec)

    print(f"[PLAYWRIGHT FILTERED] {len(valid_specs)} / {len(rendered_specs or [])}")

    if len(valid_specs) >= 5:
        print("[PLAYWRIGHT DIRECT — NO LLM]")

        return {
            "identity": {
                "brand": brand,
                "model": model,
                "barcode": barcode
            },
            "claims": valid_specs
        }

    if api_specs and len(api_specs) >= 5:

        print("[API SPECS USED — SKIPPING DOM + LLM]")

        return {
            "identity": {
                "brand": brand,
                "model": model,
                "barcode": barcode
            },
            "claims": api_specs
        }

    claims = []

    cluster_size = len(jsonld_specs)

    for attr, val in jsonld_specs:

        if not attr or not val:
            continue

        if not any(c.isalnum() for c in attr):
            continue

        if not passes_structural_validation(attr, val, cluster_size):
            continue

        v = str(val).strip().lower()

        if any(x in v for x in ["http://", "https://", ".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            continue

        if not passes_spec_gate(attr, val):
            continue

        if not is_valid_claim(attr, val):
            continue

        value, unit = split_value_unit(val)

        claims.append({
            "attribute": attr,
            "value": value,
            "unit": unit
        })

    structured_specs = extract_specs_by_structure(soup)

    cluster_size = len(structured_specs)

    for attr, val in structured_specs:

        if not any(c.isalnum() for c in attr):
            continue

        if not passes_structural_validation(attr, val, cluster_size):
            continue

        if not passes_spec_gate(attr, val):
            continue

        if not is_valid_claim(attr, val):
            continue

        value, unit = split_value_unit(val)

        claims.append({
            "attribute": attr,
            "value": value,
            "unit": unit
        })

    dedupe = {}

    for c in claims:

        attr = c.get("attribute")
        val = c.get("value")

        if not attr or not val:
            continue

        if not is_valid_claim(attr, val):
            continue

        key = (attr.lower(), str(val).lower())

        dedupe[key] = {
            "attribute": attr,
            "value": val,
            "unit": c.get("unit")
        }
  
    claims = list(dedupe.values())

    if len(claims) < 5:
        print("[REJECTED PAGE — LOW SIGNAL]")
        return {
            "identity": {
                "brand": brand,
                "model": model,
                "barcode": barcode
            },
            "claims": []
        }

    print("\n----------- FINAL PARSED PAGE -----------")
    print("Brand:", brand)
    print("Model:", model)
    print("Barcode:", barcode)
    print("Claims:", claims)
    print("----------------------------------------")

    if claims and model:
        process_and_store_claims(
            product_model=model,
            raw_claims=claims,
            domain=domain
        )

    return {
        "identity": {
            "brand": brand,
            "model": model,
            "barcode": barcode
        },
        "claims": claims
    }