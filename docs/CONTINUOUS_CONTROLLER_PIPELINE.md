# Continuous controller production path

This work lives in `csned-inl/clarity-standalone` on branch
`codex/pendulum-controller-pipeline`. It starts from the reviewed rotary
inverted-pendulum source-model commit and does not modify the original three
discrete-action controller paths.

## Current contract and its consequence

The pendulum `#NeuralRequirement` defines one exact real-valued action:

```text
proposedMotorVoltage = -K * (observed state - reference)
```

This contract leaves no policy choice. The first GRU artifact is therefore an
oracle-cloned approximation of the source feedback law, always deployed with
the symbolic equality shield. It is useful for exercising the continuous
observation/action production path, but it is not described as autonomous RL.
Reward-driven policy optimization becomes meaningful only after the SysML
contract defines a permissive state-dependent safe-action set.

## Pipeline stages

1. Parse the SysML source and require exactly one `Real` neural output.
2. Recognize only a top-level equality that isolates that output. Unsupported
   logical shapes fail closed.
3. Compile the other side of the equality into a typed action oracle. The
   implementation contains no pendulum variable names, coefficients, gains,
   or model dispatch.
4. Generate the SMV transition system and assert that the neural output was
   emitted as `real`, not `boolean`.
5. Run each emitted nuXmv invariant as an independent obligation before
   training. Every obligation has its own SMV file, process timeout,
   transcript, and verdict. A failed, timed-out, inconclusive, or missing
   obligation cannot produce a final controller artifact.
6. Generate reachable oracle-cloning data by running the SysML process with
   the exact symbolic shield.
7. Train the original-size controller backbone: two 64-wide `tanh` encoder
   layers, a 64-unit GRU, a scalar Gaussian action head, and a value head.
8. Evaluate the GRU plus symbolic shield in the SysML simulator. Publish only
   if completed evaluation reports no requirement violation or evaluation
   error.

The action distribution is not clipped inside the network. The source-level
shield chooses the required proposed voltage, and the SysML amplifier owns the
physical +/-10 V saturation. This preserves the distinction between proposed
and executed action and avoids incorrect log probabilities from post-sampling
clipping.

## VM preparation

Preparation does not import PyTorch:

```bash
python continuous_pipeline.py \
  --output runs/pendulum-prepare
```

That writes:

- `continuous_interface.json`
- `formal/model.smv`
- `formal/extract.log`
- `preparation.json`
- `summary.json`

Without `--nuxmv`, the summary says `generated_not_proved` and
`training_ready: false`. This is an inspection result, not a certificate.

## Proved training run

On a runner with Python, NumPy, PyTorch, and nuXmv:

```bash
python continuous_pipeline.py \
  --output runs/pendulum-gru \
  --nuxmv /path/to/nuXmv \
  --train \
  --device auto
```

`auto` selects CUDA first, Apple MPS second, and CPU last. Consequently, an
Apple-silicon Mac with an MPS-enabled PyTorch installation uses its GPU without
a Mac-specific model implementation.

The default training configuration uses 2,000 reachable oracle samples, 100
cloning epochs, 100 shielded evaluation episodes, a 1 ms process step, and a
6,000-step episode cap. These values are CLI parameters and should be reduced
for a runner smoke test before a full job.

The resulting `final/shielded_policy.pt` is never a standalone safety artifact.
Its `training_report.json` states both `requires_runtime_shield: true` and
`learned_policy_autonomous: false`.

## Not implemented yet

- A permissive continuous safe-action interval or polytope.
- Autonomous continuous PPO optimization inside such a safe set.
- The GitHub-to-personal-Mac compute-request workflow for this repository.
- A completed nuXmv proof run for the corrected real-valued SMV model.

## Pendulum verification corrections

The first combined proof attempt exposed two representation defects that are
now guarded by focused tests:

- Controller sends made directly from an action named `step` must be coupled
  to the connected receiver. Otherwise the receiver's message availability
  and payload become unconstrained verification inputs. The extractor now
  handles direct-send steps without changing the established
  `step -> named scan action` path.
- A stored command must be checked against the exact observation used to
  compute it. The pendulum controller now stores four controller-owned
  observation fields alongside `lastProposedVoltage`; the state-feedback
  obligation uses that snapshot instead of newer encoder state.

The staged extraction test also found and removed an unsound auxiliary rule
that asserted nonnegativity for every real-valued step target. Only integer
targets that the generated transition relation explicitly clamps to a
nonnegative range may receive that strengthening invariant.

Formal results are intentionally not aggregated into one nuXmv invocation.
`formal.py` extracts once and writes one isolated model and transcript per
`INVARSPEC`. It continues after a timeout or counterexample so a difficult
balance-envelope obligation cannot hide the voltage or state-feedback
results. Overall `verified` is true only if every emitted obligation is
individually proved.

At corrected source commit `44a28b41224f92454b38b3eae09588cc3ccafb09`,
the repository's 34 tests pass.  nuXmv independently proves the motor-voltage
requirement, the controller state-feedback requirement, and both frozen target
bound auxiliaries.  The balance-envelope requirement alone reaches bound 17
and times out after 300 seconds.  It is therefore unresolved, the aggregate
certificate is false, and controller training remains blocked.

Those are separate increments. In particular, the compute bridge must not be
used to conceal an unproved formal stage or to label exact feedback cloning as
autonomous reinforcement learning.
