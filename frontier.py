# frontier.py

from __future__ import annotations
from typing import Optional
from db import get_db


# -------------------------------------------------------
# ADD URL TO FRONTIER
# -------------------------------------------------------

def add_to_frontier(url: str, discovered_from_token: str | None = None, depth: int = 0):

    conn = get_db()

    conn.execute(
        """
        INSERT OR IGNORE INTO crawl_frontier
        (url, discovered_from_token, depth, status)
        VALUES (?, ?, ?, 'pending')
        """,
        (url, discovered_from_token, depth),
    )

    conn.commit()
    conn.close()


# -------------------------------------------------------
# GET NEXT URL TO CRAWL
# -------------------------------------------------------

def get_next_frontier_url() -> Optional[str]:

    conn = get_db()

    row = conn.execute(
        """
        SELECT id, url
        FROM crawl_frontier
        WHERE status = 'pending'
        ORDER BY priority_score DESC, id ASC
        LIMIT 1
        """
    ).fetchone()

    if not row:
        conn.close()
        return None

    frontier_id, url = row

    conn.execute(
        """
        UPDATE crawl_frontier
        SET status='processing'
        WHERE id=?
        """,
        (frontier_id,),
    )

    conn.commit()
    conn.close()

    return url


# -------------------------------------------------------
# MARK COMPLETE
# -------------------------------------------------------

def mark_frontier_complete(url: str):

    conn = get_db()

    conn.execute(
        """
        UPDATE crawl_frontier
        SET status='complete'
        WHERE url=?
        """,
        (url,),
    )

    conn.commit()
    conn.close()


# -------------------------------------------------------
# MARK FAILED (NEW)
# -------------------------------------------------------

def mark_frontier_failed(url: str):

    conn = get_db()

    conn.execute(
        """
        UPDATE crawl_frontier
        SET status='failed'
        WHERE url=?
        """,
        (url,),
    )

    conn.commit()
    conn.close()


# -------------------------------------------------------
# RESET STUCK URLS
# -------------------------------------------------------

def reset_processing_urls():

    conn = get_db()

    conn.execute(
        """
        UPDATE crawl_frontier
        SET status='pending'
        WHERE status='processing'
        """
    )

    conn.commit()
    conn.close()

def reset_frontier_pending():

    conn = get_db()

    conn.execute(
        """
        UPDATE crawl_frontier
        SET status = 'pending'
        WHERE status = 'processing'
        """
    )

    conn.commit()
    conn.close()