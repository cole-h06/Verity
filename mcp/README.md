# MCP Interface

Experimental MCP server for querying the Verity credibility graph.

In a redefining technological shift of AI systems increasingly generating and consuming information, the problem shifts from information retrieval to information verification. 

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
