# Experiment 9 - Synthetic Agreement Graph

Date: June 22, 2026

## Hypothesis

Experiment 8 revealed that increasing agreement weighting changed the order of credibility rankings by only small amounts.

Did we under-weight the agreement mechanism, or perhaps the graph was simply too sparse to support agreement properly?
Let's find out:

## Synthetic Graph

```text
A -> X

B -> X

C -> Y
```

## Agreement Scores

```text
X = 1.00

Y = 0.50
```

## Result

```text
A 0.50

B 0.50

C 0.00
```

## Observation

The final credibility rankings were affected significantly by the agreement mechanism.

The sources attached to the fully agreed claim dominated the graph, whereas the source attached to the partially agreed claim collapsed toward zero.

## Conclusion

This shows that the agreement mechanism can significantly contribute to overall credibility and the effects witnessed in Experiment 8 were almost certainly due to graph sparseness.
