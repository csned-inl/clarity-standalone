Historical held-action prototype. Superseded as the active path by `../gem-pmsm-1ms/README.md`, which has 3000 actual plant steps.

# One-millisecond policy interval

The source SysML model is unchanged (SHA-256
`2e4b6d62a6a7ad7382d160ef12759b48e966905b1286970b38cbf9139b989d6f`).
Its plant period remains 0.0001 s and its three-second horizon remains 30000
source ticks. The experimental policy now chooses one abc voltage action every
0.001 s; the held-action environment repeats that action for ten source ticks.
There are 3000 policy decisions per full episode. This is an external
sample-and-hold controller specialization, not a replacement motor equation.

`pmsm_training_comparison.py` defaults to `--control-repeat 10 --max-steps 3000
--stage motor-timing`. `--control-repeat 1` retains the source decision rate;
use `--max-steps 30000` for a full three-second source-rate episode. The shared
pipeline's PMSM default is also 3000 policy decisions. The primitive
`environment()` helper retains repeat 1 for source-conformance tests; training
and the runtime preflight explicitly select repeat 10.

Every internal source transition refreshes the abc-to-dq transform at its actual
native rotor angle, advances the adaptive DOPRI5 service over 100 microseconds,
checks the original current prohibition, and advances the original reference
generator. No sigma, random seed protocol, physical parameter, current limit,
or native numerical tolerance is changed. A training episode ends if any
internal sample violates the requirement. The motor itself has no post-fault
absorbing state. Original internal events and all sampled speed errors are
retained; reported MAE/RMSE therefore use the same physical sampling grid.

## Certificate and execution

Candidate evaluation uses an isolated plant and solver. For each of the ten
native source transitions it computes the existing local ideal-ODE enclosure,
native numerical discrepancy, cushion, and upward-rounded score. It refreshes
the transform from that staged native rotor angle before the next transition.
Acceptance requires ten valid checkpoints and `max(checkpoint scores) <= 1`.
Failed partial prefixes cannot be accepted. The fallback search uses a
full-decision Euler approximation for candidate generation only; every returned
action must pass the complete checkpoint certificate.

Each local ideal companion starts at the exact staged native state. This
certifies the composed numerical simulator response at every source checkpoint;
it does not propagate a single physical-ODE uncertainty tube through all ten
angle-dependent transforms. No new physical-ODE or hardware safety proof is
claimed. That distinction is explicit in candidate and shield reports.

All prepared endpoints, solver timestamps, work arrays, and links between
checkpoints are checked before any execution. Execution consumes those same ten
cached native responses and performs no second numerical integration.

## Reward and timing

Let `g` be the original per-source-tick discount. One policy transition receives
`sum(g**j * r[j] for j in range(10))`, with the tracking cap and intervention
cost applied in the original per-tick units before summation. This preserves
the discounted objective for held actions. The outer discount is `g**10` and
the GAE factor lambda is similarly rescaled. In the motor-timing stage:

- gamma = exp(-0.001/0.5), approximately 0.998002;
- lambda = exp(-0.001/0.1)/gamma, approximately 0.992032;
- discount and direct advantage-trace horizons remain 0.5 s and 0.1 s;
- the terminal training penalty accounts for the discounted sum of ten
  per-tick cost bounds; its physical-time cost budget is preserved.

The proposal correction is fixed for the held action and its penalty is charged
in the same per-tick units as tracking. This avoids weakening the intervention
penalty tenfold relative to the task reward.

## Verification inputs

The source CFG accepts `control_repeat=10`, holds the same proposal registers
for ten native solver transitions, and refreshes voltage transforms each tick.
Current-safety obligations remain at every source checkpoint; completion still
counts 30000 plant transitions. Metadata separately records 3000 policy
decisions. Source model and runtime hashes remain pinned.

The conditional nuXmv checker retains its safety theorem and negative controls,
and additionally checks an inductive conjunction of counter bounds, the
policy/plant clock relation, and three-second completion. The supporting clock
relation is proved together with the completion condition rather than silently
assumed. These are conditional interface and scheduler checks, not a universal
proof of the Python/native implementation.
