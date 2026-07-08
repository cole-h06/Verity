# Source Dependencies

If two sources agree, it does not necessarily mean that they are independent.

The same claim may be asserted by two independent sources because they both independently arrived at the same information.

Alternatively, the same claim may be asserted by two dependent sources based on one copying the other.

From the perspective of a credibility propagation algorithm, these two instances appear identical despite the different evidence.

As a consequence, a large number of dependent sources can create an illusion of high consensus despite a lack of independent evidence. In contrast, a small number of independent sources can be worth more than a large number of sources with copied information.

## Research Question

Is there a way to determine source dependencies based exclusively on the source-claim graph?

## Hypothesis

Let's suppose Source B depends on Source A.

In that case, the information asserted by Source B should typically be more completely contained within the information asserted by Source A than vice versa.

This directional asymmetry of the relationship could, perhaps, be used to infer the dependency that does not require introducing explicit citation or metadata.

## Thought Experiments

First, let's test the ability of directional inclusion asymmetry to distinguish source dependencies from independent agreement based only on the graph structure. There are a couple different cases:

### Case 1 - Perfect Copying

Source A:

{1, 2, 3, 4, 5}

Source B:

{1, 2, 3, 4, 5}

What should we expect?

- The two sources appear structurally identical.
- A dependency likely exists.
- The direction of the dependency cannot be determined from graph structure alone.
- The graph cannot distinguish between:
  - Source A copied Source B.
  - Source B copied Source A.
  - Both copied a hidden third source.

### Case 2: Partial Copying

Source A:

{1, 2, 3, 4, 5}

Source B:

{1, 2, 3}

What should we expect?

- All of Source B's assertions have been made by Source A as well.
- Source B is a proper subset of Source A.
- Source A only partially explains Source B in the reverse order.
- This is why directional asymmetry occurs and supports the hypothesis.

### Case 3: Independent Agreement

Source A:

{1, 2, 3, 4, 5}

Source B:

{2, 4, 6, 8}

What should we expect?

- There is agreement present between the two independent sources on some claims.
- The hypothesis cannot conclude a dependency relationship that does not exist.
- Graph alone may or may not distinguish this case; this has yet to be determined through testing.

### Case 4: Common Upstream Source

Source C:

{1, 2, 3, 4, 5}

Source A:

{1, 2, 3}

Source B:

{1, 2, 4}

What should we expect?

- Information on both sources roots from a common upstream source.
- None of the sources depend on each other.
- In cases where Source C is not in the graph, this scenario cannot be distinguished from copying.
- This is one of the limitations of a graph-based method.

## Open Questions

- How is this best modeled mathematically / what concept fits best?
- Is there a way or method to figure out the dependencies purely based on graph structure?
- How do we incorporate inferred dependencies into credibility propagation?
- How do we model partial dependencies?
- How do we handle common upstream sources?
