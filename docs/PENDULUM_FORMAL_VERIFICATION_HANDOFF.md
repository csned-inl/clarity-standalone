# Pendulum formal verification: failures and timeout diagnosis

This handoff concerns `csned-inl/clarity-standalone` commit
`dd9d9d6f7a435df3e11ab28b7158c16046766cdd` on
`codex/pendulum-controller-pipeline`, specifically
`sysml-models/rotary-inverted-pendulum/model.sysml` and the SMV emitted by
`sysml-models/mc-extract.py`. The observations below apply to that exact
revision and generated model. They do not certify or refute the intended
closed-loop SysML design independently of the extractor.

The [diagnostic archive](PENDULUM_FORMAL_VERIFICATION_DIAGNOSTICS_dd9d.tar.gz)
contains the exact temporary SMV variants, extractor experiment, diffs, and
nuXmv logs used for the segmented checks below. Its baseline is the pinned
`dd9d9d6f` revision; the temporary variants are not the later source fixes.

## Result of the submitted proof jobs

| Job | Worker | Result |
| --- | --- | --- |
| [`standalone-pendulum-formal-dd9d-20261004-2250`](https://github.com/csned-inl/clarity-standalone/blob/compute-results/results/standalone-pendulum-formal-dd9d-20261004-2250.json) | `macbook` | Exit 1 after `formal.verify()` failed. Its retained `verification.json` reported nuXmv return code 124, zero completed invariant results, and three emitted invariants. |
| [`standalone-pendulum-formal-blink-dd9d-20261004-2253`](https://github.com/csned-inl/clarity-standalone/blob/compute-results/results/standalone-pendulum-formal-blink-dd9d-20261004-2253.json) | `ubuntu-blink` | Same exit and retained verification outcome. Its `nuxmv.txt` reached bound 8 and ended with `TIMEOUT`. |

The direct timeout is in `nuXmv`, invoked with `check_invar_ic3` and a
300-second subprocess limit by [`formal.py`](https://github.com/csned-inl/clarity-standalone/blob/dd9d9d6f7a435df3e11ab28b7158c16046766cdd/formal.py).
These are not worker-dispatch or missing-dependency failures. The generated
Blink SMV has SHA-256
`72e4949d907e34b0617093a1db862e17e938c3db98a8c3d094cb6dc9d0534a9e`;
its source SysML SHA-256 is
`2f49f700943bd31915b14c202b0ac5607944cbaf3ba47b28c3d61ef7985be3ca`.

## Confirmed problems in the generated verification model

### 1. Controller output does not drive the amplifier

The SysML source explicitly connects `controller.proposalPort` to
`amplifier.proposalPort` and sends `command.volts :=
policyCall.proposedMotorVoltage`. In the generated SMV, however,
`amplifier_proposalPort_MotorVoltageCommand_available : boolean` and
`amplifier_proposal_volts : real` remain unconstrained `IVAR`s. There is no
`DEFINE` or `TRANS` relation tying either to the controller's send or to
`controller_command_volts`. The latter is updated from the policy output but
is not used by the amplifier. The controller policy equality itself is present
as a `TRANS` constraint; it does not constrain the separate amplifier inputs.

Consequently the verifier can choose a fresh amplifier voltage and delivery
event independently at every step. This is a model/extractor coupling defect,
not evidence that the actual intended controller emits those voltages. The
relevant source locations are
[`model.sysml`](https://github.com/csned-inl/clarity-standalone/blob/dd9d9d6f7a435df3e11ab28b7158c16046766cdd/sysml-models/rotary-inverted-pendulum/model.sysml)
and the connect/trigger coupling phases of
[`mc-extract.py`](https://github.com/csned-inl/clarity-standalone/blob/dd9d9d6f7a435df3e11ab28b7158c16046766cdd/sysml-models/mc-extract.py).

The specific extractor omission is now identified: its action-body coupling
pass [skips every action named `step`](https://github.com/csned-inl/clarity-standalone/blob/dd9d9d6f7a435df3e11ab28b7158c16046766cdd/sysml-models/mc-extract.py#L877-L892),
while this model [sends the command directly from
`step`](https://github.com/csned-inl/clarity-standalone/blob/dd9d9d6f7a435df3e11ab28b7158c16046766cdd/sysml-models/rotary-inverted-pendulum/model.sysml#L303-L318).
In a temporary extractor copy, removing that exclusion caused it to emit
controller-to-amplifier aliases, confirming the missed action-body path.
That single-line experiment also introduced `scan_phase` and repeated send
conditions, so it is **not** a validated source fix.

### 2. The balance-envelope invariant is false in that generated model

`Stay Within Balance Controller Envelope` requires the physical pendulum
angle to remain between `-0.349065850399` and `+0.349065850399` radians.
Because the amplifier input is free, an allowed execution delivers +10 V on
every step. Independently stepping the generated model's exact recurrence
from its zero initial state gives a pendulum angle of approximately
`0.353131015535` radians at step 80 (0.08 s), above the specified upper
limit. The amplifier still obeys its ±10 V clamp. Thus the invariant is
actually false for the emitted transition system; extending the timeout
cannot turn that same model into a valid proof. This trace is a recurrence
calculation, not a counterexample emitted by the timed-out IC3 run.

An 80-step exact-recurrence comparison with the amplifier driven by the
controller's policy output and the target set to the model's +90-degree
endpoint stayed inside the envelope (peak absolute angle about `0.128187315`
radians). This removes the particular free-input witness for that scenario;
it does not prove the invariant for every target and every time. An isolated
IC3 check of the controller-coupled diagnostic model also timed out after
300 seconds, so whether the intended closed-loop design satisfies the
unbounded envelope property remains open.

### 3. The state-feedback invariant compares different sample times

The generated model sets
`next(controller_lastProposedVoltage)` from a policy expression over the
current `encoder_reading_*` variables. Its
`Controller Supplies State Feedback` `INVARSPEC` compares the resulting
`controller_lastProposedVoltage` against an expression over the current
`encoder_sampled*` and `encoder_estimated*` variables. The reading variables
lag those sampled/estimated variables in the generated `next(...)`
assignments. The equality therefore does not describe the same observation
used to choose the recorded command. An isolated check of this property
returned `false` in about 0.15 s; a recurrence check found a mismatch by
step 6 (0.006 s). The appropriate comparison must use the values observed
when that command was computed, with the intended sample timing made explicit.
The property still returned `false` (1.78 s) when the amplifier was coupled
to the policy output. A temporary property that stored the four
`encoder_reading_*` values used for each command and compared
`controller_lastProposedVoltage` to those stored values returned `true`
(0.02 s). This isolates the sample-time mismatch from the amplifier defect.

## Segmented diagnostic tests on `ubuntu-blink`

Each nuXmv check used the same generated transition system and original
`check_invar_ic3` method, with only the named temporary change. The limit was
300 seconds per check. No change in this table was committed to the standalone
source or deployed to the runner.

| Isolated check | Temporary change | Verdict / elapsed time | Interpretation |
| --- | --- | --- | --- |
| Voltage range | Only this `INVARSPEC` retained | `true`, 0.03 s | The amplifier clamp property is provable. |
| State feedback | Only this `INVARSPEC` retained | `false`, 0.15 s | Original timing comparison has a counterexample. |
| State feedback with controller-to-amplifier connection | Replace the amplifier availability `IVAR` by `TRUE` and its voltage `IVAR` by `controller_policyCall_proposedMotorVoltage` | `false`, 1.78 s | Connecting the amplifier does not repair the feedback property. |
| State feedback with observed-input snapshot | Record the four `encoder_reading_*` inputs alongside each command; compare the command with that snapshot | `true`, 0.02 s | Correcting the comparison time repairs this diagnostic property. |
| Balance envelope | Only this `INVARSPEC` retained | Timeout, 300.01 s; last reported bound 8 | The original false property is hard for IC3 to falsify. |
| Balance envelope with amplifier input disabled | Set availability to `FALSE` and voltage to `0.0` | `true`, 0.07 s | Removing the free motor input makes the zero-state plant remain within the envelope; this is a diagnostic control, not the intended controller. |
| Balance envelope with controller-to-amplifier connection | Availability `TRUE`; voltage equals policy output | Timeout, 300.00 s; last reported bound 7 | Coupling removes the known arbitrary-input defect but does not produce an unbounded proof within the limit. |

The controller-to-amplifier diagnostic changed only two SMV declarations:

```smv
amplifier_proposalPort_MotorVoltageCommand_available := TRUE;
amplifier_proposal_volts := controller_policyCall_proposedMotorVoltage;
```

The exact-recurrence witness for the original generated model used +10 V at
each amplifier event: step 79 was about `0.344401168` radians and step 80
about `0.353131016` radians, crossing the `0.349065850399` limit. The same
80-step recurrence with the controller-connected diagnostic and +90-degree
target peaked at about `0.128187315` radians. These are bounded trace
calculations, not unbounded formal proofs.

A separate attempt to use `check_invar_bmc_inc -k 80 -a falsification` did
not run: nuXmv reported `Impossible to build a boolean FSM with infinite
precision variables`. Thus this bounded command cannot replace IC3 for the
model's real-valued state without a different verification formulation.

## Other contributors to the observed timeout and poor diagnostics

| Observation | What it establishes |
| --- | --- |
| Isolated `Motor Voltage Within Authorized Range` check returned `true` in 0.03 s. | This property is readily provable for the generated clamp. It is not the source of the long proof search. |
| Isolated original envelope check timed out at 300 s and bound 8; the controller-coupled variant timed out at 300 s and bound 7. | Splitting out the property identifies the envelope check as the long-running obligation. The free-input violating trace is 80 steps long; connecting the input alone does not make IC3 finish. |
| The SMV uses many real-valued plant, estimator, command, and derivative state variables, rational arithmetic, and a 1 ms step. | These features enlarge the symbolic arithmetic search. Their individual cost has not been measured, so no single one is established as the independent root cause of the 300-second runtime. |
| The target arm angle is a real-valued `FROZENVAR` constrained only to ±π/2 at initialization. | The proof covers a continuum of target scenarios rather than one fixed target, adding symbolic scope. Its separate runtime contribution has not been measured. |
| `formal.py` runs one `check_invar_ic3` command over all three emitted `INVARSPEC`s. | A slow property can prevent a result for the other properties. The timed-out transcript has zero completed verdicts even though isolated checks can establish true or false outcomes. |
| The extractor comments say real-valued `INVARSPEC`s require k-induction, while the proof wrapper selects IC3. | The implementation and its own method note disagree. The evidence does not establish that switching proof engines alone would resolve these failures. |
| On `verify()` failure, `continuous_pipeline.py` raises before writing `preparation.json` or `summary.json`; the request then tries to read the nonexistent `summary.json`. | GitHub gets a generic traceback rather than the retained `verification.json` detail. This reporting defect obscures the timeout and property failures; it does not cause the nuXmv timeout. |

## Disposition of the three requirements at this revision

| Requirement | Evidence-based status |
| --- | --- |
| `Motor Voltage Within Authorized Range` | Proved in an isolated check of the emitted model. |
| `Stay Within Balance Controller Envelope` | False in the emitted model because amplifier inputs are unconstrained; 80-step recurrence witness. A temporary controller-connected version also timed out after 300 s, so its unbounded status remains unknown. |
| `Controller Supplies State Feedback` | Disproved in an isolated check because the invariant compares mismatched sample times. |

The original combined jobs did **not** prove any of the three properties:
both expired before nuXmv printed an invariant verdict. The isolated checks
and recurrence analysis above are separate diagnostics of the same generated
transition system.


## Corrected staged result

The diagnostics above were addressed on
`codex/pendulum-controller-pipeline` through commit
`44a28b41224f92454b38b3eae09588cc3ccafb09`.  This section supersedes the
old revision's disposition; it does not rewrite the historical evidence.

Corrections made:

- direct sends from a controller `step` action are coupled to the connected
  receiver instead of remaining free verification inputs;
- duplicate aliases from multiple receiver guard transitions are collapsed;
- real-valued state is no longer given an unsound blanket nonnegativity
  strengthening invariant;
- controller observations are explicitly latched with
  `lastProposedVoltage`, and the state-feedback requirement uses that exact
  snapshot;
- an accepted local item in a controller step is lowered through its connected
  sender instead of producing undefined `controller_reading_*` names;
- the amplifier receives the latched `controller_command_volts` value rather
  than a live policy expression evaluated at a later scan phase;
- sensor synchronisation invariants are restricted to response-item fields and
  are not generated for ordinary actuator state; and
- every emitted invariant is run in a separate nuXmv process with its own
  model, timeout, transcript, and verdict.  A failure or timeout no longer
  hides the other results.

Staged evidence for the corrected commit:

| Check | Result |
| --- | --- |
| Repository suite, request `standalone-pendulum-tests-44a2-20261005-0202` | 34 tests passed. |
| Motor-voltage requirement | Independently proved by nuXmv. |
| Controller state-feedback requirement | Independently proved by nuXmv. |
| Two frozen target-bound auxiliary invariants | Independently proved by nuXmv. |
| Balance-envelope requirement, request `standalone-pendulum-envelope-44a2-20261005-0206` | Timed out after 300 seconds at bound 17, with no proof or counterexample. |

The corrected emitted model has exactly five invariant obligations.  Four are
proved and the envelope obligation is unresolved.  Therefore the aggregate
verification result is **not proved**, and the pipeline must continue to block
training.  The timeout must not be reported as either safety or unsafety.

## Exact affine envelope certificate

The remaining envelope obligation now has a direct unbounded proof path.  The
generated SMV transition relation is compiled into an exact-rational
`AffineTransitionSystem`; the compiler mechanically composes physical scan
phases 0 and 1 and then derives the closed-loop recurrence `x' = A x + B r +
c`.  No plant or controller matrix is handwritten in the certifier.

For the current model, the certificate checks 2,600 physical cycles exactly
and then proves a 2,000-cycle block contraction.  The exact block infinity
norm is below 0.289.  The same proof bounds every intermediate state in each
block, including the executed amplifier voltage, so the unsaturated affine
branch used to derive the recurrence is closed rather than assumed.  The
reported maxima are below 0.152 radians in the finite prefix, below 0.049
radians in the unbounded tail, and below 7.911 volts in the unbounded tail,
against the model's 0.349065850399-radian and 10-volt limits.

The fast path is fail-closed: an unrecognized nonlinear expression, ambiguous
scan phase, unsupported parameterization, failed contraction, or open actuator
mode returns no proof.  nuXmv remains responsible for the other four isolated
obligations.  Full implementation and soundness boundaries are documented in
[PENDULUM_AFFINE_ENVELOPE_CERTIFICATE.md](PENDULUM_AFFINE_ENVELOPE_CERTIFICATE.md).
