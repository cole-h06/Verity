def is_duplicate_sku(
    conn,
    domain,
    sku
):
    if not sku or not domain:
        return False

    row = conn.execute("""
        SELECT 1
        FROM crawled_pages cp
        JOIN raw_claims rc
            ON rc.page_id = cp.id
        JOIN sources s
            ON rc.source_id = s.id
        WHERE s.domain = ?
        AND rc.attribute = 'sku'
        AND rc.value_string = ?
        LIMIT 1
    """, (
        domain,
        sku
    )).fetchone()

    return bool(row)