Active timing correction: see `../gem-pmsm-1ms/README.md`. The current runner uses 3000 actual 1-ms plant steps; the held-action reward aggregation described below is historical.

# Staged PMSM training corrections

These are experimental training settings, not claims about the source motor.
`model.sysml`, the source solver, current constraint, reference generator,
100-microsecond source plant period, policy architecture, optimizer, and
three-second episode limit are unchanged by these stages. The runner now
defaults to a one-millisecond held policy decision; see CONTROL_INTERVAL.md
for the clock, checkpoint-shield, and reward-aggregation extension.

## Stage 1: reward (`--stage reward`)

Retain the old learner discount 0.9 and GAE lambda 0.95 to isolate reward changes.
Both comparison arms retain tracking feedback. The punishment arm subtracts an
intervention cost instead of replacing tracking feedback with that cost.

For a nonviolating transition, with speed error `e` in RPM and correction
`c = ||raw_proposal - executed_action||_2` in normalized phase-voltage units:

```
tracking = -min(abs(e) / 8000, 1)
pass_through_reward = tracking
punishment_reward = tracking - 0.025 * c / (1 + c)
```

The intervention predicate retains the existing correction tolerance of 1e-6.
Corrections include actuator-domain clipping as well as current-safety filtering.
The existing bounded correction formula is retained; its default cap changes
from 1 to 0.025 and its action scale from 10 to 1. A correction of one normalized
action unit costs 0.0125, equivalent to 100 RPM of tracking error when the
tracking cap is inactive. The maximum intervention cost is 0.025, equivalent to
200 RPM. These are explicit pilot calibration choices, not source-derived or
experimentally established optimal weights. Both remain configurable.

The training-only tracking cap activates beyond 8000 RPM error. It provides an
actual bounded step cost for terminal-penalty calibration; the source model does
not impose a speed prohibition or guarantee that tracking errors stay below
8000 RPM. Original source rewards and physical MAE/RMSE remain unmodified in
reports. Training and evaluation also count capped transitions and sum the
intervention costs separately.

For an actual executed violation, end the episode as before, but use a shared
training terminal reward at least as negative as:

```
-(1 + penalty_cap) / (1 - gamma)
```

Both comparison arms use this same terminal objective (approximately -10.25
in Stage 1). Every nonviolating step costs at most `1 + penalty_cap`; the
formula therefore prevents terminating immediately from improving on even the
worst infinite discounted continuation from that point. The source violation
reward remains -10 and is recorded separately. This calibration follows GEM's
discount-dependent terminal-cost principle and includes our added cost.

## Stage 2: motor timing (`--stage motor-timing`, runner default)

Retain all Stage 1 reward settings. Set discount and advantage trace lengths
using physical time:

```
dt = 0.0001 seconds
discount_time = 0.5 seconds
trace_time = 0.1 seconds
gamma = exp(-dt / discount_time)       # 0.9998000199986667
lambda = exp(-dt / trace_time)/gamma  # 0.9992003199146837
```

The values above describe the original source decision rate. At the new
one-millisecond decision rate gamma is approximately 0.998002 and lambda
approximately 0.992032; the same physical horizons are preserved.

The direct GAE weighting is `(gamma * lambda)^k`, so a reward 100 ms later
retains exp(-1) of its direct contribution. Increasing gamma alone while
retaining lambda 0.95 would leave this weighting with only a 1.94 ms time
constant. This does not assert that a shorter GAE trace is always wrong: lambda
trades estimator bias against variance and depends on critic accuracy.

The model's uncoupled electrical L/R constants are 20.56 and 66.67 ms. These
are not the mechanical speed-settling time. The 0.5 s discount and 0.1 s trace
are provisional experimental choices to retain feedback beyond those electrical
scales, not a measured optimal speed-control horizon. The terminal training
reward is recalculated to approximately -5125.51 with the same cost budget.

## Evaluation order

1. Verify Stage 1 reward ordering on identical transitions and unchanged plant
   trajectories. Verify tracking caps and the terminal-cost bound.
2. Verify the actual GAE recurrence retains the declared delayed contribution.
3. Exercise both stages and both shielded modes on the server GPU, including
   an optimizer update and checkpoint reload. Short runs establish wiring and
   numerical execution only, not tracking quality.
4. For a learning comparison, compare the reward stage first, then motor timing,
   using identical seeds, initial weights, episode lengths, and update budgets.
   Report physical MAE/RMSE, intervention counts, executed violations, blockage,
   capped tracking steps, and task versus intervention reward separately.

Settings are saved before training in `training/settings.json`, in checkpoints,
and in final training/comparison reports. Old running processes and old reports
retain their original settings; these changes apply to newly started runs.

## Basis

- GEM's local source `src/gym_electric_motor/reward_functions/weighted_sum_of_errors.py`
  defines the normalized negative tracking reward and a terminal violation
  reward based on minimum ongoing reward and the agent's discount. Our SysML
  model preserves its original defaults. The bounded training adapter and added
  intervention cost above are documented experimental extensions.
- Markgraf et al., *Safe Reinforcement Learning using Action Projection*,
  [Section 7.1, equations 19–20](https://arxiv.org/html/2509.12833v2#S7.SS1):
  subtract an intervention cost from the executed-action reward. Their common
  example uses squared correction distance. We retain the existing bounded
  distance cost and explicitly calibrate its scale instead.
- Tallec et al., *Making Deep Q-learning Methods Robust to Time Discretization*,
  [author explanation](https://ctallec.github.io/continuous-rl/): express
  discounting and rewards consistently with physical time. This supplies the
  physical discount principle, not a claim that their Q-learning convergence
  results establish PPO performance.
- Schulman et al., *High-Dimensional Continuous Control Using Generalized
  Advantage Estimation*, [Section 3, equation 16](https://arxiv.org/html/1506.02438#S3):
  the direct temporal weighting uses gamma times lambda, with a bias–variance
  tradeoff.
