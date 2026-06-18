# Experiment 8 - Isolation Dynamics

Date: June 18, 2026

In Experiment 6, I noted that multiple sources collapsed to zero credibility.

Examples included:

```text
lenovo.com
hp.com
dell.com
pcrichard.com
bjs.com
```

All sources with this behavior shared the same property:

```text
unique_ratio = 1.0
```

Every claim they asserted was supported by only a single source.

At that time I speculated that the graph propagation was somehow penalizing isolated claims, although it was not clear to me how. The mechanism was unclear.

I wanted to better understand this effect, so I moved away from the full database and constructed a minimal toy graph:

The goal was to directly simulate the verifier interpretation of the system:

```text
source -> claim -> source
```

rather than relying on fixed-point propagation alone.

Toy graph:

```text
A -- C1 -- B
A -- C2 -- B

D -- C3
D -- C4
```

Graph structure:

```text
Source A supports claims C1 and C2.

Source B supports claims C1 and C2.

Source D supports claims C3 and C4.

Claims C3 and C4 are only supported by D.
```

Notice that there are two connected components.

Component 1

```text
A -- C1 -- B
A -- C2 -- B
```

Component 2

```text
D -- C3
D -- C4
```

A verifier repeatedly performs:

```text
source -> claim -> source
```

choosing a random outgoing edge at each step.

I simulated 100,000 rounds, starting the verifier in each connected component.

Starting from A:

```text
A = 50.01%
B = 49.99%
```

Starting from D:

```text
D = 100.00%
```

Now it should be clear.

When the verifier begins inside the connected component containing A and B, it randomly goes between the two nodes:

```text
A -> C1 -> B
B -> C2 -> A
```

and so on...

However, when the verifier begins at D:

```text
D -> C3 -> D
D -> C4 -> D
```

the verifier never escapes.

The verifier simply can't escape from the component.

So it seems the collapse in Exp 6 is not caused by a source being false.
To me, it seems to be a consequence of graph connectivity.

A source whose claims are entirely unique becomes disconnected from the rest of the graph.

The verifier can no longer travel between that source and the larger network.

The current system therefore appears to measure:

```text
connectedness
```

rather than:

```text
truth
```

This raises another important point.

It is important to realize that isolated claims don't mean incorrect ones, just as a widely shared claim does not mean it is correct.

Our graph only captures whether or not information connects to other information.

It does not yet distinguish between shared truths, shared falsehoods, isolated truths, or isolated falsehoods.

Thus the question for my next experiment is not whether or not sources connect to other sources but whether those sources connect together in the way they have to to show consensus (or in this case, agreement on value) which is something the current system does not measure.