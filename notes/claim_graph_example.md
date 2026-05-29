# Claim Graph Example

Suppose several sources publish specifications about the same laptop display.

One group of sources asserts:

- screen_brightness_nits = 300 nits

while another source asserts:

- screen_brightness_nits = 250 nits

These values are not merely isolated rows, they can be represented as graph claims.

Each source forms an edge to the claim it asserts:

source_id -> claim_id

This creates a structure where:
- sources connect to claims
- claims accumulate support from multiple sources
- conflicting claims compete for reinforcement

![Assertions Graph](../data/assertions.png)

![Claims Graph](../data/claims.png)

In the above images,

- claim 892 = screen_brightness_nits : 300 nits
- claim 1047 = screen_brightness_nits : 250 nits

If multiple independent sources support claim 892, the graph may repeatedly revisit that region during recursive propagation.

But, it would be naive to classify each source as independent by default. This is because agreement alone does not necessarily imply independence. Sources tend to copy what other sources claim.

### Dependency Propagation

![Dependency Propagation](../images/dependency_propagation.png)

In the graph above:

- S1 supports claim C1
- S2 may reference or inherit from S1
- Therefore, C2 may accumulate reinforcement originating from a partially shared dependency, not truly independent verification.

This is a reason I believe the graph topology itself may contain important credibility signals that is worth exploring.
