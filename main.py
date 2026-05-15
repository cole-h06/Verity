import asyncio
import random
from db import (
    initialize_database,
    get_db,
    get_pending,
    mark_complete,
    mark_failed,
    reset_product_urls
)
from scout import run_scout
from miner import run_miner
from search_bridge import run_search_bridge
from config import RETAILER_CONFIG, IDENTITY_RESET_MODE, REBUILD_MODE

print("CONFIG LOADED:", RETAILER_CONFIG.get("bestbuy.com"))

BATCH_SIZE = 2
MAX_FAILS = 20

async def run():
    initialize_database()

    #await run_scout()

    await asyncio.sleep(random.uniform(15, 25))

    fail_count = 0
    processed = 0

    while True:
        conn = get_db()

        if IDENTITY_RESET_MODE:
            reset_product_urls(conn)

        if REBUILD_MODE:
            print("[REBUILD MODE] scanning all URLs")

            rows = conn.execute("""
                SELECT *
                FROM pending_crawl
                ORDER BY id
                LIMIT ?
            """, (BATCH_SIZE,)).fetchall()

        else:
            rows = get_pending(conn, limit=BATCH_SIZE)

        if not rows:
            conn.close()
            break

        for row in rows:
            url = row["url"]
            category = row["category"]

            status_row = conn.execute(
                "SELECT status FROM pending_crawl WHERE url=?",
                (url,)
            ).fetchone()

            if status_row and status_row["status"] == "failed":
                print(f"[MAIN SKIP FAILED] {url}")
                continue

            print(f"[MINER] {url} ({category})")

            result = None

            for attempt in range(3):
                try:
                    result = await run_miner(url, category)

                    if result != "retry":
                        break

                except Exception as e:
                    print(f"[ERROR] {e}")
                    result = "retry"

                if result == "retry":
                    wait_time = random.uniform(10, 30)
                    print(f"[RETRY WRAPPER {attempt+1}] waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)

            if result == "retry":
                print("[RETRY]")
                fail_count += 1

            elif result:
                print("[SUCCESS]")

                if not result.get("needs_enrichment"):
                    mark_complete(conn, url)

                fail_count = 0

            else:
                print("[FAILED]")
                mark_failed(conn, url)
                fail_count += 1

            processed += 1
            print(f"[PROGRESS] {processed} processed")

            if fail_count >= MAX_FAILS:
                print("[STOP] Too many failures")
                conn.commit()
                conn.close()
                return

            await asyncio.sleep(random.uniform(8, 15))

        conn.commit()
        conn.close()

if __name__ == "__main__":
    asyncio.run(run())