# server.py
#
# Experimental MCP interface for Verity
#
# The goal is to expose the credibility graph to AI agents
#
# Long-term goal:
# domain-agnostic source credibility infrastructure


import sqlite3

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("verity")


DB = "../verity_v1.db"


def get_db():

    # we must create a fresh connection for each request
    # to keep the server simple and stateless

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    return conn


@mcp.tool()
def ping() -> str:
    """
    Simple connectivity test.
    """

    return "Verity MCP online."


@mcp.tool()
def get_source_credibility(domain: str) -> dict:
    """
    Return the credibility score for a source.
    """

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            source_id,
            domain
        FROM sources
        WHERE domain = ?
    """, (domain,))

    row = cursor.fetchone()

    conn.close()

    if row is None:
        return {
            "found": False
        }

    # placeholder until propagation scores
    # are written back into the database

    return {
        "found": True,
        "source_id": row["source_id"],
        "domain": row["domain"],
        "credibility": None
    }


@mcp.tool()
def get_claim_support(claim_id: int) -> dict:
    """
    Return all sources supporting a claim.
    """

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            s.domain
        FROM assertions a
        JOIN sources s
            ON a.source_id = s.source_id
        WHERE a.claim_id = ?
    """, (claim_id,))

    rows = cursor.fetchall()

    conn.close()

    return {
        "claim_id": claim_id,
        "supporting_sources": [
            row["domain"]
            for row in rows
        ],
        "support_count": len(rows)
    }


@mcp.tool()
def find_conflicting_claims(
    product_id: str,
    attribute: str
) -> dict:
    """
    Return all asserted values for an attribute.
    """

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            claim_id,
            value_string
        FROM claims
        WHERE product_id = ?
        AND attribute = ?
    """, (
        product_id,
        attribute
    ))

    rows = cursor.fetchall()

    conn.close()

    return {
        "product_id": product_id,
        "attribute": attribute,
        "values": [
            {
                "claim_id": row["claim_id"],
                "value": row["value_string"]
            }
            for row in rows
        ]
    }


@mcp.tool()
def trace_claim(claim_id: int) -> dict:
    """
    Return the sources asserting a claim.
    """

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            c.attribute,
            c.value_string,
            s.domain
        FROM claims c
        JOIN assertions a
            ON c.claim_id = a.claim_id
        JOIN sources s
            ON a.source_id = s.source_id
        WHERE c.claim_id = ?
    """, (claim_id,))

    rows = cursor.fetchall()

    conn.close()

    if not rows:
        return {
            "found": False
        }

    # agents should inspect evidence
    # rather than blindly trust values

    return {
        "found": True,
        "claim_id": claim_id,
        "attribute": rows[0]["attribute"],
        "value": rows[0]["value_string"],
        "supporting_sources": [
            row["domain"]
            for row in rows
        ]
    }


if __name__ == "__main__":

    # launch MCP over stdio
    # local agent clients can connect directly

    mcp.run()
