# MCP Interface

Verity exposes an experimental MCP server that computes structural credibility within networks of sources and claims.

It stores a persistent credibility graph and returns deterministically derived credibility signals through the emerging [Model Context Protocol (MCP)](https://modelcontextprotocol.io). By analyzing how sources connect to each other through the claims they assert, Verity can reason about the overall structure of the information itself instead of the underlying content of data.

This allows the engine to measure provenance, corroboration, conflicting information, and source dependencies without requiring the server to interpret the data itself.

This implementation is intended to serve as the reference MCP interface for the Verity inference engine and serves as the basis for self-hosted and cloud deployments.
