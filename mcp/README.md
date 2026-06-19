# MCP Interface

Experimental MCP server for querying the Verity credibility graph.

If Search provided a map to help humans find information on the web, AI systems face a different challenge:
determining which information to trust.

Verity exposes an experimental MCP server that allows AI agents
to query source credibility and claim support.

The current implementation focuses on e-commerce product specifications as a
real-world testing ground but the interface itself is domain agnostic.

Current dataset:
e-commerce product specifications.

Long-term goal:
build trust infrastructure for how AI systems evaluate information.

Example tools:

- get_source_credibility()
- get_claim_support()
- find_conflicting_claims()
- trace_claim()
