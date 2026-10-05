# Continuous GRU shield-training comparison

This is an experimental comparison for the proved rotary-inverted-pendulum
model on `codex/pendulum-controller-pipeline`.  It does not change the formal
proof and it does not label any learned checkpoint as independently safe.

## Three training modes

All modes begin with identical GRU weights, scenario seed, PPO settings, and
episode limits.

| Mode | Plant receives | PPO credits | Unsafe execution ends episode |
| --- | --- | --- | --- |
| `unshielded_safety_terminate` | Original proposal | Original proposal | On `#Prohibition` violation |
| `shielded_executed_credit` | Shield replacement | Executed replacement | No |
| `shielded_proposal_credit` | Shield replacement | Original proposal | No |

A shield intervention never terminates an episode. It is a safe transition.
The earlier immediate-termination unshielded mode supplied only one-step
episodes because nearly every Gaussian proposal violated the exact controller
equality. The earlier never-terminate mode allowed physically unsafe dynamics
to run for the complete horizon and diverged. The replacement middle mode
allows controller-contract mismatch to produce proposal-error learning signal
but terminates when an executed trajectory violates an actual
`#Prohibition`, such as leaving the physical balance envelope.

## Reward

Terminal success remains `+1`. The raw simulator's step reward is normalized
for the 6,000-step horizon: ordinary elapsed time has a maximum episode budget
of `-0.10`, and shield intervention has a maximum episode budget of `-0.05`.
Thus a nonterminal step receives `-0.10 / max_steps` or, if replaced by the
shield, `-0.05 / max_steps`. A terminal success step receives only `+1`.

Modes that credit the original proposal use

```text
-penalty_cap * abs(proposal - required_action) /
    (action_error_scale + abs(proposal - required_action))
```

The current configuration uses `penalty_cap = 1.0` and a 10 V error scale.
The penalty approaches `-1` but never becomes flat at any finite error. A
noncompliant original proposal receives this punishment **instead of** the
environment reward; reward and punishment are never applied simultaneously.
A proposal within the contract tolerance receives the ordinary environment
reward. The continuous penalty avoids assigning the same value to almost
every sample from a Gaussian policy.

The executed-credit shield mode deliberately omits this proposal penalty.  It
tests the alternative in which learning credit follows the replacement that
the plant actually received. Every transition receives exactly one of task
success, proposal punishment, override punishment, time cost, or truncation;
these values are not added together.

## Outputs and interpretation

`continuous_training_experiments.py` records success, truncation, unsafe
executions, shield interventions, proposal error, episode reward, and a
separate experimental checkpoint for each mode.  Checkpoints have
`deployable: false`.  Shielded evaluation demonstrates the composite
controller only; unshielded evaluation measures the learned proposal without
claiming formal safety.

The formal model certificate remains independent.  Training success cannot
replace it, and an experimental failure cannot refute it.
