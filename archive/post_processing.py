import sqlite3
import re
import os
from collections import defaultdict, Counter
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "knowledge_graph.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def fetch_raw(product_model):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT r.id, r.domain,
               json_extract(j.value, '$.attribute'),
               json_extract(j.value, '$.value')
        FROM raw_specs r,
             json_each(r.spec_json) j
        WHERE r.product_model = ?
    """, (product_model,))

    rows = cur.fetchall()
    conn.close()
    return rows

def migrate_units(attribute, value, current_unit):
    if current_unit is not None:
        return value, current_unit

    match = re.search(r'(\d+\.?\d*)\s*(.*)', str(value))

    if match:
        new_val = match.group(1)
        new_unit = match.group(2).strip().strip('.')

        if not new_unit:
            attr_unit = re.search(r'\((.*?)\)', str(attribute))
            new_unit = attr_unit.group(1) if attr_unit else None

        try:
            return float(new_val), new_unit
        except:
            return value, new_unit

    return value, current_unit

def atomize_blobs(attribute, value):
    matches = re.findall(r'(\d+\.?\d*)\s*([a-zA-Z]+)', str(value))

    if len(matches) > 1:
        return [{"attribute": attribute, "value": m[0], "unit": m[1]} for m in matches]

    return None

def normalize(attr, val):
    attr_clean = str(attr).lower().strip()
    val_str = str(val).lower().strip()

    val_processed, unit = migrate_units(attr_clean, val_str, None)

    if isinstance(val_processed, float):
        return attr_clean, val_processed, None, unit

    match = re.search(r'(\d+\.?\d*)', val_str)

    if match:
        return attr_clean, float(match.group(1)), None, unit

    return attr_clean, None, val_str, None

def build_rows(raw_rows):
    rows = []

    for raw_id, domain, attr, val in raw_rows:
        if not attr or not val:
            continue

        atomized = atomize_blobs(attr, val)

        if atomized:
            for item in atomized:
                attr_clean, num, text, unit = normalize(item["attribute"], item["value"])

                rows.append({
                    "raw_id": raw_id,
                    "source_domain": domain,
                    "normalized_attribute": attr_clean,
                    "raw_attribute": attr,
                    "raw_value": val,
                    "value_numeric": num,
                    "value_string": text,
                    "unit": item["unit"]
                })
        else:
            attr_clean, num, text, unit = normalize(attr, val)

            rows.append({
                "raw_id": raw_id,
                "source_domain": domain,
                "normalized_attribute": attr_clean,
                "raw_attribute": attr,
                "raw_value": val,
                "value_numeric": num,
                "value_string": text,
                "unit": unit
            })

    return rows

model = SentenceTransformer('all-MiniLM-L6-v2')

def cluster_attributes(rows, threshold=0.9):
    attrs = list(set(r["normalized_attribute"] for r in rows))
    print(f"Embedding {len(attrs)} attributes...")
    embeddings = model.encode(attrs)

    clusters = []
    used = set()

    for i, attr in enumerate(attrs):
        if i in used:
            continue

        group = [attr]
        used.add(i)

        for j in range(i + 1, len(attrs)):
            if j in used:
                continue

            sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]

            if sim > threshold:
                group.append(attrs[j])
                used.add(j)

        clusters.append(group)

    return clusters

def slugify(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')

def get_source_types(domains):
    conn = get_connection()
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in domains)

    cur.execute(f"""
        SELECT domain, source_type
        FROM sources
        WHERE domain IN ({placeholders})
    """, tuple(domains))

    rows = cur.fetchall()
    conn.close()

    return {domain: stype for domain, stype in rows}

def get_source_ids(domains):
    conn = get_connection()
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in domains)

    cur.execute(f"""
        SELECT domain, id
        FROM sources
        WHERE domain IN ({placeholders})
    """, tuple(domains))

    rows = cur.fetchall()
    conn.close()

    return {domain: sid for domain, sid in rows}

def choose_canonical(group, rows):
    candidates = [r for r in rows if r["normalized_attribute"] in group]

    domains = list(set(r["source_domain"] for r in candidates))
    source_types = get_source_types(domains)

    for c in candidates:
        domain = c["source_domain"]
        if source_types.get(domain) == "manufacturer":
            return slugify(c["normalized_attribute"])

    attr_counts = Counter([c["normalized_attribute"] for c in candidates])
    winner = attr_counts.most_common(1)[0][0]

    return slugify(winner)

def build_canonical_map(clusters, rows):
    mapping = {}

    for group in clusters:
        canonical = choose_canonical(group, rows)

        for attr in group:
            mapping[attr] = canonical

    return mapping

def apply_canonical_map(rows, canonical_map):
    new_rows = []

    for r in rows:
        canonical = canonical_map.get(r["normalized_attribute"], r["normalized_attribute"])
        r["normalized_attribute"] = canonical
        new_rows.append(r)

    return new_rows

def filter_by_source_frequency(rows, min_sources=2):
    attr_sources = defaultdict(set)

    for r in rows:
        attr_sources[r["normalized_attribute"]].add(r["source_domain"])

    valid_attrs = {
        attr for attr, sources in attr_sources.items()
        if len(sources) >= min_sources
    }

    return [r for r in rows if r["normalized_attribute"] in valid_attrs]

def group_claims(rows):
    grouped = defaultdict(list)

    for r in rows:
        key = r["normalized_attribute"]

        val = r["value_numeric"] if r["value_numeric"] is not None else r["value_string"]
        unit = r["unit"]

        grouped[(key, val, unit)].append(r)

    return grouped

def insert_normalized_claims(grouped):
    conn = get_connection()
    cur = conn.cursor()

    for (attr, val, unit), records in grouped.items():
        domains = list(set(r["source_domain"] for r in records))
        source_ids_map = get_source_ids(domains)

        for r in records:
            source_id = source_ids_map.get(r["source_domain"])

            is_numeric = 1 if r["value_numeric"] is not None else 0
            is_boolean = 1 if str(r["value_string"]).lower() in ["yes", "no", "true", "false"] else 0
            is_categorical = 1 if not is_numeric and not is_boolean else 0

            cur.execute("""
                INSERT INTO normalized_claims (
                    raw_id,
                    source_id,
                    source_domain,
                    raw_attribute,
                    raw_value,
                    raw_unit,
                    section_header,
                    normalized_attribute,
                    value_numeric,
                    value_string,
                    unit,
                    is_numeric,
                    is_boolean,
                    is_categorical,
                    is_rejected,
                    rejection_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r["raw_id"],
                source_id,
                r["source_domain"],
                r["raw_attribute"],
                r["raw_value"],
                r["unit"],
                None,
                attr,
                r["value_numeric"],
                r["value_string"],
                unit,
                is_numeric,
                is_boolean,
                is_categorical,
                0,
                None
            ))

    conn.commit()
    conn.close()

def analyze_product(product_model):
    print("Fetching raw...")
    raw = fetch_raw(product_model)
    print(f"Raw rows: {len(raw)}")

    print("Building rows...")
    rows = build_rows(raw)
    print(f"Normalized rows: {len(rows)}")

    print("Clustering attributes...")
    clusters = cluster_attributes(rows)
    print(f"Clusters: {len(clusters)}")

    print("Building canonical map...")
    canonical_map = build_canonical_map(clusters, rows)

    print("Applying canonical map...")
    rows = apply_canonical_map(rows, canonical_map)

    print("Filtering by source frequency...")
    rows = filter_by_source_frequency(rows)
    print(f"Rows after filter: {len(rows)}")

    print("Grouping claims...")
    grouped = group_claims(rows)
    print(f"Grouped claims: {len(grouped)}")

    print("Inserting into DB...")
    insert_normalized_claims(grouped)

    print("Done.")
    return grouped

if __name__ == "__main__":
    product_model = "CC70F30S2DAA"
    results = analyze_product(product_model)

    for k, v in results.items():
        print(k, len(v))