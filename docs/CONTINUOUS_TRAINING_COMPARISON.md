# Continuous GRU shield-training comparison

This is an experimental comparison for the proved rotary-inverted-pendulum
model on `codex/pendulum-controller-pipeline`.  It does not change the formal
proof and it does not label any learned checkpoint as independently safe.

## Four training modes

All modes begin with identical GRU weights, scenario seed, PPO settings, and
episode limits.

| Mode | Plant receives | PPO credits | Unsafe execution ends episode |
| --- | --- | --- | --- |
| `unshielded_terminate` | Original proposal | Original proposal | Yes |
| `unshielded_continue` | Original proposal | Original proposal | No |
| `shielded_executed_credit` | Shield replacement | Executed replacement | No |
| `shielded_proposal_credit` | Shield replacement | Original proposal | No |

A shield intervention never terminates an episode.  It is a safe transition.
Only the two unshielded modes differ in whether an action that is actually
executed and violates a requirement terminates the episode.

## Reward

The simulator retains the existing CLARITY rewards: `+1` for terminal
success, `-0.01` while running, and `0` at truncation. Modes that credit the
original proposal use

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
the plant actually received.

## Outputs and interpretation

`continuous_training_experiments.py` records success, truncation, unsafe
executions, shield interventions, proposal error, episode reward, and a
separate experimental checkpoint for each mode.  Checkpoints have
`deployable: false`.  Shielded evaluation demonstrates the composite
controller only; unshielded evaluation measures the learned proposal without
claiming formal safety.

The formal model certificate remains independent.  Training success cannot
replace it, and an experimental failure cannot refute it.
