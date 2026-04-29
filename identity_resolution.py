from __future__ import annotations
import sqlite3
import re

from identity import (
    is_model_alias,
    pick_canonical_model
)

DB_PATH = "knowledge_graph.db"


# -------------------------------------------------------
# GTIN / BARCODE NORMALIZATION
# -------------------------------------------------------

def normalize_gtin(value: str):
    if not value:
        return None

    digits = re.sub(r"\D", "", value)

    if not digits:
        return None

    # normalize to GTIN-14
    return digits.zfill(14)


# -------------------------------------------------------
# LOAD DATA
# -------------------------------------------------------

def load_rows(conn):
    rows = conn.execute("""
        SELECT id, url, domain, product_model, barcode
        FROM raw_specs
        WHERE product_model IS NOT NULL
    """).fetchall()

    return rows


# -------------------------------------------------------
# CLUSTER ROWS (BARCODE → MODEL)
# -------------------------------------------------------

def cluster_rows(rows):

    clusters = []

    for row in rows:

        model = row["product_model"]
        barcode = normalize_gtin(row["barcode"])

        if not model and not barcode:
            continue

        placed = False

        for cluster in clusters:

            for existing in cluster:

                existing_model = existing["product_model"]
                existing_barcode = normalize_gtin(existing["barcode"])

                # --------------------------------------------------
                # 1. BARCODE MATCH (HARD OVERRIDE)
                # --------------------------------------------------
                if barcode and existing_barcode and barcode == existing_barcode:
                    cluster.append(row)
                    placed = True
                    break

                # --------------------------------------------------
                # 2. MODEL MATCH (FALLBACK)
                # --------------------------------------------------
                if is_model_alias(model, existing_model):
                    cluster.append(row)
                    placed = True
                    break

            if placed:
                break

        if not placed:
            clusters.append([row])

    return clusters


# -------------------------------------------------------
# SAVE RESULTS
# -------------------------------------------------------

def save_clusters(conn, clusters):

    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cluster_id INTEGER,
            canonical_model TEXT,
            barcode TEXT,
            source_url TEXT,
            source_model TEXT
        )
    """)

    conn.execute("DELETE FROM product_clusters")

    cluster_id = 0

    for cluster in clusters:

        models = [r["product_model"] for r in cluster if r["product_model"]]
        canonical = pick_canonical_model(models)

        # --------------------------------------------------
        # RESOLVE CLUSTER BARCODE (CONSENSUS)
        # --------------------------------------------------

        barcodes = []

        for r in cluster:
            b = normalize_gtin(r["barcode"])
            if b:
                barcodes.append(b)

        cluster_barcode = None
        if barcodes:
            # pick most common barcode
            from collections import Counter
            cluster_barcode = Counter(barcodes).most_common(1)[0][0]

        # --------------------------------------------------

        for row in cluster:
            conn.execute("""
                INSERT INTO product_clusters (
                    cluster_id,
                    canonical_model,
                    barcode,
                    source_url,
                    source_model
                )
                VALUES (?, ?, ?, ?, ?)
            """, (
                cluster_id,
                canonical,
                cluster_barcode,
                row["url"],
                row["product_model"]
            ))

        cluster_id += 1

    conn.commit()


# -------------------------------------------------------
# MAIN
# -------------------------------------------------------

def run_identity_resolution():

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    print("[IDENTITY] Loading rows...")
    rows = load_rows(conn)

    print(f"[IDENTITY] Rows loaded: {len(rows)}")

    print("[IDENTITY] Clustering...")
    clusters = cluster_rows(rows)

    print(f"[IDENTITY] Clusters formed: {len(clusters)}")

    print("[IDENTITY] Saving...")
    save_clusters(conn, clusters)

    print("[IDENTITY] Done.")


if __name__ == "__main__":
    run_identity_resolution()