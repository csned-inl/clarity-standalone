# Continuous-action and symbolic-verification handoff — 2026-10-05

## Read this first

The active implementation repository is **`csned-inl/clarity-standalone`**. The active continuous-motor branch is **`codex/hall-sensored-bldc-model`**. The pending training request is pinned to source commit **`429e7d87efe21164836ec93eebca344122fd5e4f`**.

The older **`csned-inl/fitter-artifact`** repository is useful for the generic symbolic-process, Markov, structural-discretization, and method-validation implementations, but it is **not model-source ground truth**. Do not copy an OT model from `fitter-artifact` over a reviewed `clarity-standalone` model. The standalone SysML sources and their pinned reference material control model fidelity.

The governing architecture is:

> Parse the mathematical process specified by SysML directly, preserve physical state, sensed state, fixed context, timing, action execution, and safety properties as distinct symbols, and use the least expensive sound proof method that recognizes the resulting structure. Unsupported structure passes to a stronger fallback; it is never guessed, silently simplified, or certified by timeout.

For the Markov work, the non-negotiable narrower statement remains:

> Give Z3 only the minimal information needed to prove whether the buffered controller-facing process is Markov. Do not recreate the simulator control graph.

## Repositories and current branches

| Repository | Branch / revision | Purpose |
| --- | --- | --- |
| `csned-inl/clarity-standalone` | `codex/hall-sensored-bldc-model`, training source pinned at `429e7d8` | Reviewed continuous-action SysML models, extraction, safety proofs, training, and runner-facing experiments |
| `csned-inl/clarity-standalone` | `compute-requests` | Requests consumed by the personal compute bridge |
| `csned-inl/clarity-standalone` | `compute-results` | Runner result receipts |
| `csned-inl/fitter-artifact` | `codex/thermostat-symbolic-machine`, currently `7749466` | Generic direct-SysML symbolic process, structural Markov/discretization checks, Z3 fallback, and method-logic validation |

Do not merge the two repositories conceptually: `clarity-standalone` supplies the reviewed model and executable continuous-controller pipeline; `fitter-artifact` contains generic certification research that may be ported only deliberately.

## What has been built

### 1. Direct symbolic process representation

The earlier Markov effort was corrected after an implementation mistakenly encoded the simulator control graph and caused solver blow-up. The replacement treats the SysML mathematical specification as the primitive:

- true physical variables remain distinct from delayed or sampled sensor variables;
- proposed, shielded, and physically executed actions remain distinct;
- fixed process context and scenario inputs are explicit;
- transition equations, inequalities, obligations, prohibitions, delays, tolerances, and terminal conditions are represented directly;
- source hashes and fail-closed shape checks prevent silent semantic drift.

Relevant generic files in `fitter-artifact` include:

- `src/clarity/certification/symbolic_process.py`
- `src/clarity/certification/ot_markov.py`
- `src/clarity/certification/structural_markov.py`
- `src/clarity/certification/controller_class_analysis.py`
- `src/clarity/certification/structural_discretization.py`
- `src/clarity/certification/discretization_semantic_validation.py`
- `src/clarity/certification/method_implementation_validation.py`
- `scripts/prove_markov.py`
- `scripts/certify_discretization.py`
- `scripts/validate_symbolic_methods.py`

The pipeline uses a cascade:

1. inexpensive syntactic/structural recognition;
2. exact algebraic proof for a recognized subclass;
3. SMT/model-checking fallback for unresolved semantic obligations.

A fast-path checker is one-way: it may return a positive certificate only for a recognized sufficient condition. Otherwise it must pass through. Failure to recognize a model is not a negative result.

The logical validity of the reusable proof rules is checked separately from per-model certification. Per-model runs should not rerun the entire meta-validation suite unless the proof method itself changed.

### 2. Structural discretization safety

The symbolic-process work was also applied to discretization safety. The intended fast path is the familiar calculus argument made executable:

- extract the continuous/affine rate relation and the safety margin from SysML;
- compute a sound rate or Lipschitz bound;
- combine the bound with the chosen interval;
- prove that inter-sample movement cannot consume the available margin;
- pass unrecognized or insufficient cases to semantic fallback.

The method-validation and per-model certification programs are separate. See in `fitter-artifact`:

- `docs/STRUCTURAL_DISCRETIZATION_SAFETY.md`
- `docs/SYMBOLIC_PROCESS_LOGIC.md`
- `.github/workflows/symbolic-method-validation.yml`

Do not interpret a structural refusal as a safety failure, and do not interpret finite simulation as an unbounded proof.

## Continuous-action model 1: rotary inverted pendulum

Source:

- `sysml-models/rotary-inverted-pendulum/model.sysml`
- `sysml-models/rotary-inverted-pendulum/README.md`
- `sysml-models/rotary-inverted-pendulum/REVIEW.md`

Pipeline:

- `continuous_pipeline.py`
- `symbolic_transition.py`
- `pendulum_envelope_certificate.py`
- `docs/CONTINUOUS_CONTROLLER_PIPELINE.md`
- `docs/PENDULUM_AFFINE_ENVELOPE_CERTIFICATE.md`

Important corrections already made:

- direct sends from an action named `step` are coupled to the connected receiver;
- controller state-feedback is checked against the exact stored observation used to compute the command, not a later sensor state;
- the extractor no longer invents nonnegativity for arbitrary real-valued step targets;
- nuXmv obligations run independently, so one hard obligation cannot hide quick successes or counterexamples.

The pendulum proof is hybrid but still source-derived:

- nuXmv proves the local voltage, controller-feedback, and frozen-target obligations;
- the difficult unbounded balance envelope is recognized as an affine transition system compiled from the emitted SMV;
- exact rational finite-prefix plus contraction reasoning proves the envelope and the amplifier branch needed by that reasoning.

This is not a handwritten plant-matrix proof. `symbolic_transition.py` parses the emitted transition relation, composes the recognized phases, slices irrelevant state, and produces exact `A`, `B`, and `c`. Unsupported structure fails closed.

The original pendulum `#NeuralRequirement` identifies an exact feedback output, so the first GRU pipeline is oracle cloning plus an equality shield, not autonomous RL. Later continuous PPO experiments should not erase that distinction.

## Continuous-action model 2: Hall-sensored BLDC motor

Source and provenance:

- `sysml-models/hall-sensored-bldc/model.sysml`
- `sysml-models/hall-sensored-bldc/README.md`
- `sysml-models/hall-sensored-bldc/REVIEW.md`
- `sysml-models/hall-sensored-bldc/SOURCE_CONFORMANCE_AUDIT.md`

The model is centered on the selected NXP Hall-sensored six-step BLDC reference and its compatible parameter material. It is not an average of unrelated motor specifications. Source comments distinguish published values, project-level reductions, and explicit assumptions.

The model preserves:

- physical rotor angle, speed, and energized-pair current;
- Hall sampling and six-period speed estimation;
- proposed duty, bounded proposal, and executed duty;
- Hall validity and the exact commutation table;
- the plant-facing current-safe projection;
- target, completion tolerance, and controller-held command;
- scenario inputs and model assumptions.

Current safety obligations include normalized executed duty, invalid-Hall shutdown, valid phase commutation, physical and projected pair-current bounds, feasibility of the current-safe interval, physical speed envelope, and the neural bounded-duty contract. Task completion is speed tracking within the declared tolerance, distinct from safety.

Verification:

- `hall_motor_verification.py` extracts a fail-closed safety contract from the model;
- a structural certificate proves observer synchronization, current-projection algebra, projection regions, feasibility over the authorized envelope, target feasibility, Hall shutdown, and the commutation table;
- it emits a compact real-arithmetic SMV model;
- nuXmv checks the emitted obligations independently.

At source commit `429e7d8`, the corrected validation campaign had:

- 36/36 runner tests passing;
- all seven motor nuXmv obligations proved;
- short Mac MPS PPO smoke runs for both shielded modes with zero unsafe executed steps in training and evaluation.

The training entry point is `hall_motor_training.py`. The two relevant modes are:

- `shielded_executed_credit`: environment/task reward follows the action actually executed by the process, with a small intervention cost;
- `shielded_proposal_credit`: PPO likelihood remains attached to the sampled proposal, while the reward penalizes divergence between the proposal and what the process executed.

PPO must always record the sampled proposal in its likelihood calculation. Scoring a projected action under the proposal density is wrong. The process-facing reward may nevertheless depend on the actually executed action.

The trained checkpoints remain experimental and non-deployable until the full evaluation gate passes.

## Pending MacBook training

The requested replacement full run has been submitted:

- request ID: `standalone-motor-500ep-10ms-20261005-1752`
- compute-request commit: `ac6d03f86af0d3cee26e317db2c659160d0153e1`
- worker: `macbook`, macOS arm64, PyTorch MPS
- source commit: `429e7d87efe21164836ec93eebca344122fd5e4f`
- modes: both shielded modes
- training episodes: 500 per mode
- evaluation episodes: 100 per mode
- controller decision interval: 10 ms
- controller decisions per episode: 300
- intended physical episode horizon: 3 seconds
- seed: 42

Request file:

`requests/standalone-motor-500ep-10ms-20261005-1752.json` on `compute-requests`.

Expected result file:

`results/standalone-motor-500ep-10ms-20261005-1752.json` on `compute-results`.

As of this handoff, that result file had **not returned**.

The request is an intentionally temporary experiment: inside the runner worktree it changes `speedControlTicksPerUpdate` from 20 to 200, recomputes the fail-closed safety-slice digest for that temporary worktree, and then trains. It does not persist that timing change to the source branch. The next session must inspect the result before making claims and must not treat this runtime patch as the final configuration architecture.

An older request, `standalone-motor-full-shielded-20261005-1700`, asked for 2,000 episodes and 3,000 controller decisions per mode. It was still absent from `compute-results` when the smaller replacement was submitted. Do not confuse its eventual result with the 500-episode/10-ms experiment.

When the new result arrives, record at least:

| Mode | Training successes | Evaluation successes | Truncations | Mean steps | Mean reward | Shield interventions | Mean proposal error | Unsafe executed steps | Errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |

Zero unsafe execution is mandatory but not sufficient for task success. A shield can make a useless policy safe.

## Mandatory timing/parameter refactor

This is the highest-priority implementation correction after collecting the pending result.

The current pipeline makes timing changes unnecessarily difficult because related timing values appear in model fields, training code, verification extraction, comments, tests, and runner commands. That creates an inconsistency hazard.

The externally meaningful controller discretization interval—called `dt` by the user—must become one authoritative, explicit parameter. Changing it once must propagate mechanically to every downstream consumer. If the motor implementation also requires a smaller internal electrical/commutation integration substep, give that quantity a different, unambiguous name. Do not call two different intervals `dt`.

At minimum, the single controller interval must determine or validate:

- the interval between controller observations and decisions;
- the number of internal plant/commutation substeps;
- episode physical duration and controller-step limits;
- simulator scheduling;
- controller-held-action duration;
- reward/time normalization;
- buffer/history timestamps;
- discretization certificates and their margins;
- any transition matrix or recurrence compiled for proof;
- current-projection and observer timing where applicable;
- emitted nuXmv/SMT constants;
- result metadata, tests, and documentation.

Required behavior:

1. One source of truth is parsed into the symbolic/process contract.
2. Every derived duration is computed from that value, not copied as another literal.
3. The compiler rejects non-integral substep ratios where an integral ratio is required.
4. The compiler rejects disagreement between plant, observer, sensor, shield, verifier, and trainer timing.
5. Certificates include the authoritative timing value and source hash.
6. Changing timing invalidates stale certificates and checkpoints automatically.
7. Tests mutate the one authoritative parameter and verify that all downstream derived values change together.
8. No runner-time source rewriting or digest rewriting remains in the final pipeline.

Do not merely replace one hardcoded literal with several command-line defaults. The point is a typed, propagated parameter with fail-closed consistency checks.

## Immediate next actions for the new session

1. Check `compute-results` for `standalone-motor-500ep-10ms-20261005-1752.json`.
2. Summarize both modes in the table above and inspect stdout/stderr, not just exit code.
3. Determine whether 500 episodes produced meaningful task completion rather than only safe truncation.
4. Preserve the result as an experiment pinned to `429e7d8`; do not retroactively reinterpret it after source changes.
5. Design and implement the authoritative controller-`dt` propagation described above.
6. Run focused timing/consistency tests before rerunning full verification or training.
7. Only after those focused tests pass, rerun motor structural verification, each nuXmv obligation, and a short two-mode PPO smoke.
8. Submit another full training job only if the refactored smoke is consistent and safe.

## Compute bridge

Use GitHub as the asynchronous boundary:

- edit and pin source in the normal source branch;
- submit JSON requests on `compute-requests`;
- request the weakest adequate worker unless MPS/GPU training is specifically useful;
- read receipts from `compute-results`;
- never infer success from request disappearance or elapsed time;
- always pin the exact source commit and retain output/error tails.

The MacBook is appropriate for PyTorch MPS training. GitHub-hosted or smaller personal workers are preferable for ordinary tests and symbolic checks when their dependencies suffice.

## Soundness boundaries

- The SysML model is the modeled world. Certificates are conditional on that model and its explicit assumptions being correct.
- Model-source fidelity and proof correctness are separate obligations.
- Structural certificates apply only to their recognized subclass.
- nuXmv or Z3 timeout is inconclusive, never proof or disproof.
- Simulation can find counterexamples and training behavior; finite simulation cannot establish an unbounded universal property.
- A source hash prevents unnoticed drift but does not prove that a reviewed digest is semantically correct.
- Physical and sensor values must never be collapsed unless the model explicitly asserts equality.
- Shield presence is part of the transition system. With no shield, use identity execution; with a shield, certify the shielded process.
- The proof sees fixed context and hidden physical state even when the controller does not.
- A certificate must name its exact scope, assumptions, non-claims, source revision, and timing configuration.
