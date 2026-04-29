from db import get_db
from search_bridge import run_search_bridge

def main():
    conn = get_db()

    rows = conn.execute("""
        SELECT gtin, model, brand, title
        FROM products
        WHERE LOWER(brand) LIKE '%longhi%'
    """).fetchall()

    print(f"[FOUND PRODUCTS]: {len(rows)}")

    # allow re-search
    conn.execute("""
        DELETE FROM searched_products
        WHERE key IN (
            SELECT gtin FROM products WHERE LOWER(brand) LIKE '%longhi%'
        )
    """)
    conn.commit()

    for r in rows:
        product = {
            "gtin": r["gtin"],
            "model": r["model"],
            "brand": r["brand"],
            "title": r["title"],
            "category": "espresso"
        }

        print(f"\n[RE-RUN SEARCH] {product['gtin']} | {product['model']}")

        run_search_bridge(conn, product)

    conn.close()


if __name__ == "__main__":
    main()