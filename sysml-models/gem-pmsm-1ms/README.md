# Active 1-ms / 3000-plant-step profile

The [current work record](../../docs/PMSM_WORK_LOG.md) covers second-order
and piecewise-friction checking, completed trials, and the deferred Flow* plan.

The complete source-deviation register is in
[SPEC_DEVIATIONS.md](../gem-pmsm/SPEC_DEVIATIONS.md).

This is the active PMSM pipeline/training model. Three seconds consists of
3000 policy decisions AND 3000 scheduled plant transitions. The ten-source-tick
held-action wrapper is not used. Each candidate is checked as one complete
1-ms transition and its prepared numerical response is committed once.

The original source model remains in `../gem-pmsm/model.sysml`. Only three
numeric declarations differ, plus the introductory interval explanation:

| Declaration | Original | Active |
|---|---:|---:|
| SampledTransition.samplePeriodSeconds | 0.0001 s | 0.001 s |
| elapsedSeconds increment | 0.0001 s | 0.001 s |
| trialControlSteps | 30000 | 3000 |

Motor parameters, equations, transforms, current limit, reset state, native
DOPRI5 solver/tolerances, and source reward formula are unchanged. The rotor
transform is now refreshed every 1 ms and its resulting dq voltage is held for
that 1-ms transition. This extends the source's sampled approximation; it is
an explicit experimental timing change, not an assertion of identical fine-
and coarse-grid trajectories. Sampled current monitoring now occurs at 1 ms.

The reference generator advances once per new plant step. Its original
per-step increment distribution and clipping bounds are retained. Thus its
evolution in physical time is slower: the 500–1999-step noise-scale segments
now last 0.5–1.999 s, versus 0.05–0.1999 s. This deliberately avoids retaining
30000 hidden reference/plant updates.

Training uses one tracking sample and one possible subtractive correction
penalty per 1-ms transition. It does not sum ten old rewards. The motor-timing
stage retains the physical 0.5-s discount horizon and 0.1-s GAE trace:
gamma approximately 0.998002, lambda approximately 0.992032. With the existing
bounded tracking cost and 0.025 maximum correction cost, the shared terminal
training penalty becomes approximately -513.01. Original source rewards are
recorded separately; the source's own -10 violation output is unchanged.

The adapter recognizes the exact revised scheduler signatures. The shield
and source-CFG generator accept the explicitly pinned profile hash; arbitrary
model edits remain rejected. The compiled native transition uses t+0.001 and
completion at 3000. Conditional nuXmv checks use the same model/hash/horizon.

DOPRI5 retains adaptive internal numerical stages and the checker retains
adaptive enclosure calculations. There is no mandatory ten-plant-step loop.
Numerical simulator certificates remain distinct from a physical/hardware
safety proof. A regression counts actual ModelPlant.step calls through a full
three-second run and requires exactly 3000, with completion only on the last.
