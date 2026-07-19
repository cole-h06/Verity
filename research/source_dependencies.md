# Source Dependencies

If two sources agree, it does not necessarily mean that they are independent.

The same claim may be asserted by two independent sources because they both independently arrived at the same information.

Alternatively, the same claim may be asserted by two dependent sources based on one copying the other.

From the perspective of a credibility propagation algorithm, these two instances appear identical despite the different evidence.

As a consequence, a large number of dependent sources can create an illusion of high consensus despite a lack of independent evidence. In contrast, a small number of independent sources can contribute greater evidence than a large number of sources with copied information.

## Research Question

Is there a way to determine source dependencies based exclusively on the source-claim graph?

## Hypothesis

Let's suppose Source B depends on Source A.

In that case, the information asserted by Source B should typically be more completely contained within the information asserted by Source A than vice versa.

This directional asymmetry of the relationship could, perhaps, be used to infer the dependency that does not require introducing explicit citation or metadata.

<p align="center">
  <img src="../images/source_dependency_graph.png" width="500">
</p>

## Thought Experiments

First, let's test the ability of directional inclusion asymmetry to distinguish source dependencies from independent agreement based only on the graph structure. There are a couple different potential cases:

### Case 1 - Perfect Copying

Source A:

{1, 2, 3, 4, 5}

Source B:

{1, 2, 3, 4, 5}

Expected outcome:

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

Expected outcome:

- All of Source B's assertions have been made by Source A too.
- Source B is a proper subset of Source A.
- Source A only partially explains Source B in the reverse order.
- This is why directional asymmetry occurs and supports the hypothesis.

### Case 3: Independent Agreement

Source A:

{1, 2, 3, 4, 5}

Source B:

{2, 4, 6, 8}

Expected outcome:

- There is agreement present between the two independent sources on some claims.
- The hypothesis cannot conclude a dependency relationship that does not exist.
- Graph alone may or may not distinguish this case; it is yet to be determined.

### Case 4: Common Upstream Source

Source C:

{1, 2, 3, 4, 5}

Source A:

{1, 2, 3}

Source B:

{1, 2, 4}

Expected outcome:

- Information on both sources roots from a common upstream source.
- None of the sources depend on each other.
- In cases where Source C is not in the graph, this scenario cannot be distinguished from copying.
- This is one of the limitations of a graph-based method.

## Directional Inclusion Asymmetry (Experiment 1)

One of the things I wanted to see right away was if directional inclusion itself contains any structural signal without parameters.

To do that, I constructed for each source the set of assertions:

(product, attribute, value)

and measured between all pairs of sources:

- matching assertions
- conflicting assertions
- directional inclusion
- agreement ratio
- asymmetry

After computing the top-ranked pairs, I wrote an inspection tool to manually compare all matching and conflicting assertions between the two sources.

In addition, it became clear after analyzing the shared assertions that the disagreements were not random, but rather, were conflicting specifications for the same product.

### Results

A number of high-ranking source pairs quickly seemed to make sense.

For instance, there was a higher percentage of claims made by Target that were included in Best Buy than vice versa.

In looking at the source pairs, we found that disagreement was usually a conflicting value of the same product rather than an independent assertion.

This indicates that directional inclusion is more than just agreement. It also accounts for the extent to which one source’s information is structurally included in another’s.

### Observations

Directional inclusion asymmetry seems to provide a structural signal that can be helpful in identifying source dependencies.

On the other hand, it does not completely solve the problem.

A perfect copy cannot be distinguished from a hidden common parent source, and very small sources can lead to overinflated asymmetry scores.

The next step is to figure out whether directional inclusion will continue as a stand-alone measure or becomes one of multiple signals apart of a broader dependency model.

## Toward a Structural Dependency Model

Directional inclusion asymmetry demonstrated that, as seen in Experiment 1, useful structural information can be derived. But, it is not sufficient enough to fully characterize source dependencies.

Instead of using a single metric, I'm looking into modeling it as a hybrid function over multiple graph-derived signals which I believe is a better way it can be formally defined.

Let:

D(A, B)

be the structural dependency between sources A and B.

We define:

$$
D(A, B) = f(X_1, X_2, \ldots, X_n)
$$

where each $X_i$ refers to a distinct structural property of the relationship between two sources.

Some potential signals could include:

- directional inclusion asymmetry
- rarity of shared assertions
- structural similarity
- community overlap
- additional graph-derived dependency measures

The exact nature of f will have to be determined empirically by future experiments.

## Open Questions

- How is this best modeled mathematically / what concept fits best?
- Is there a way or method to figure out the dependencies purely based on graph structure?
- How do we incorporate inferred dependencies into credibility propagation?
- How do we model partial dependencies?
- How do we handle common upstream sources?
