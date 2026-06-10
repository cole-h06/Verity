# Experiment 1 - Initial Credibility Propagation

Date: June 10, 2026

## Setup

Sources: 24

Claims: 15,185

Initialization:

All source credibility scores initialized uniformly.

Update Rule:

Claim support = sum(source credibility)

Source credibility = average(claim support)

Repeated for 20 iterations.

## Results

Top Sources

1. jbl.com ............ 0.163609
2. belkin.com ......... 0.114268
3. bhphotovideo.com ... 0.091313

...

## Observations

The algorithm produced a non-uniform
credibility distribution after 20 iterations.

Several manufacturer sources ranked above
large retailers despite having substantially
fewer claims.

After further inspection of the highest-support claims, it turns out that many were heavily corroborated
across manufacturers and retailers.

Examples included:

- noise_cancellation = true
- impedance = 16 ohms
- frequency_response = 20 kHz

Several incorrect claims also accumulated
substantial support.

Example:

battery_capacity = 20000 hours

This may imply that Version 0 rewards
agreement, but does not distinguish between
agreement and correctness.

## Known Questions

- Should agreement be normalized?
- How should disagreement be modeled?
- How should source independence be modeled?
- Can correctness emerge from graph structure alone?
