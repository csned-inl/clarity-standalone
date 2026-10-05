# Continuous-action and symbolic-verification handoff — 2026-10-05

## Purpose and audit status

This document hands the work to a new session. It was checked against the source branches, proof documents, test files, commit history, and compute receipts rather than reconstructed only from conversation.

This revision corrects two material errors in the first draft:

1. The implemented structural discretization checker does **not** yet prove a general physical Lipschitz inter-sample bound. It proves a narrower atomic/held-state property for recognized source requirements. A derivative/Lipschitz physical-margin rule remains future work.
2. The 2,000-episode motor request is no longer pending. It returned **incomplete** with exit code 255 after only 110 episodes of its first mode. It produced useful progress lines but no completed comparison or evaluation result.

The replacement 500-episode motor request remains pending at the time of this revision.

## BLOCKING FAILURE — CONTINUOUS MODELS ARE QUARANTINED

**Do not present, publish, demonstrate, extend, train, or make verification claims from either continuous-action model until a complete timing audit and repair has been performed.** This applies to both the Hall-sensored BLDC motor and the rotary inverted pendulum. The motor is known broken with respect to timing configuration and execution cost; the pendulum must be presumed affected until independently audited because it shares the same simulator/training architecture and duplicated timing controls.

This is not a request for a compiler, transition-kernel compiler, simulator replacement, or other architectural expansion. The immediate defect is much simpler: timing that should have been controlled by one propagated parameter was independently hardcoded across the SysML, simulator adapter, trainer, proof metadata, and runner request. The previous agent is explicitly **not authorized to implement the repair**. The next session must diagnose and propose the smallest correction, obtain user approval, and only then modify source.

No existing successful test, nuXmv result, structural certificate, smoke run, or shielded-training result removes this block. Those results may remain as historical diagnostics, but model-level conclusions are quarantined until the timing audit determines exactly which claims survive.

## Non-negotiable project direction

The SysML model is the formal process being studied. The proof pipeline must compile the mathematics and constraints expressed by that model directly. It must not compile a simulator and then symbolically reconstruct the mathematics from the simulator's procedural control graph.

The central Markov rule is:

> THE PLAN IS TO GIVE THE MINIMAL AMOUNT OF INFORMATION TO Z3 TO PROVE THE BUFFERED CONTROLLER IS MARKOV. IF YOU BEGIN TO DO OTHERWISE STOP PRODUCTION IMMEDIATELY AND CALL FOR MY HELP.

The broader verification rule is:

> Preserve every distinction that can affect a theorem—physical versus sensed state, proposed versus shielded versus plant-executed action, fixed context versus observation, plant time versus controller time, and safety property versus transition assumption—and use the cheapest sound proof rule that recognizes the resulting symbolic structure. Unsupported structure passes through; it is never guessed or certified by timeout.

## Source authority and repositories

| Repository | Branch / revision | Authority and role |
| --- | --- | --- |
| `csned-inl/clarity-standalone` | `codex/hall-sensored-bldc-model`; motor training source `429e7d87efe21164836ec93eebca344122fd5e4f` | Authoritative reviewed SysML models for this work; continuous-action extraction, verification, training, and runner experiments |
| `csned-inl/clarity-standalone` | `compute-requests` | Asynchronous personal-runner requests |
| `csned-inl/clarity-standalone` | `compute-results` | Immutable runner receipts and output tails |
| `csned-inl/fitter-artifact` | `codex/thermostat-symbolic-machine`; reviewed here at `77494663012487cad802bb4b99ee940e39d43010` | Generic direct-SysML symbolic-process, Markov, structural-discretization, and method-validation research |

`fitter-artifact` is **not model-source authority**. A model copy there is usable only after a byte-for-byte identity check against the corresponding `clarity-standalone` source and recorded Git blob. Generated SMV, simulator traces, old certificates, backups, and prior agent work are also non-authoritative.

External reference fidelity and formal proof soundness are different obligations:

- the model must be traceable to one coherent authoritative process description, compatible specification family, or measured device;
- the proof must correctly establish its claim about that exact model;
- neither obligation substitutes for the other.

Do not blend unrelated device specifications to fill gaps. Missing data must be identified as a model assumption, excluded behavior, or an explicit reason the claim cannot be made.

## Direct symbolic-process and Markov work

### What replaced the failed simulator encoding

The first Markov attempt expanded the simulator control graph, scheduler paths, events, and guarded branches into Z3. It was sound in spirit but violated the goal, generated large formulas, timed out, and repeated the failure mode of the older project.

The replacement pipeline treats source equations as the primitive and builds only the controller-boundary relation required by the exact query. The symbolic representation keeps:

- physical state;
- sampled or delayed sensor state;
- proposed action;
- optional shield/execution relation;
- plant-executed action;
- fixed process context and scenario inputs;
- explicit finite memory, phase, delay, and queue state when required;
- transition equations and guards;
- observation, completion, reward, termination, and error projections;
- the exact buffer recurrence.

The simulator is outside the proof path. It remains useful for testing, counterexample replay, and training.

### Current implemented Markov profile

The generic profile in `fitter-artifact` takes one model path rather than dispatching by model name:

```text
prove_markov(model_path)
```

Relevant implementation:

- `src/clarity/certification/symbolic_process.py`
- `src/clarity/certification/ot_markov.py`
- `src/clarity/certification/structural_markov.py`
- `src/clarity/certification/controller_class_analysis.py`
- `scripts/prove_markov.py`
- `docs/OT_MARKOV_SYSML_PROFILE.md`
- `docs/SYSML_DIRECT_MARKOV_CERTIFICATION_ARCHITECTURE.md`
- `docs/BUFFER_CANDIDATE_ANALYSIS.md`

Profile 0.1 is deliberately narrow. It recognizes the structural conventions of the reviewed Thermostat, Mixing Machine, and Cruise Controller sources and currently requires Boolean policy outputs. It is not arbitrary SysML, a general probabilistic verifier, or yet the continuous-action Markov checker.

Current source-derived buffer candidates are:

| Model | Prior observations | Prior executed actions | Reason |
| --- | ---: | ---: | --- |
| Thermostat | 0 | 1 | Current observation supplies temperature and setpoint; one prior executed action reconstructs pre-decision actuator latches used by completion |
| Mixing Machine | 0 | 0 | At the policy boundary, the sampled levels plus fixed tolerance reconstruct the relevant physical values; incoming actuator state is overwritten before the selected result |
| Cruise Controller | 0 | 1 | Current observation plus one prior executed action reconstructs the selected controller-boundary result |

The current tests establish two distinct routes:

- the one-way structural fast path positively certifies all three recognized models without importing Z3 or executing a simulator;
- the generic Z3 backend independently certifies the same candidates under the supported profile, including initialization, shield totality/uniqueness, and paired successor factorization.

The candidate generator alone never certifies Markovness. An unresolved reconstruction yields no candidate. A positive certificate requires the structural theorem or the paired semantic proof.

The shield boundary is model-agnostic:

- with a recognized NeuralRequirement, the execution relation is keep-or-replace/projection as compiled from the source contract;
- without a shield contract, execution is identity;
- the Markov theorem is about the resulting shielded or unshielded controller-facing process, whichever is actually specified.

### Structural-analysis scope

`controller_class_analysis.py` statically classifies algebraic and dependency shape. It can eliminate impossible controller classes and choose promising proof/training fallbacks without running the process. Shape analysis alone is not a semantic Markov proof unless a reviewed structural theorem explicitly connects that shape to the property.

The intended cascade is:

1. syntactic/source-shape checks;
2. one-way structural theorem for a recognized subclass;
3. compact Z3/nuXmv obligation for the semantic residue;
4. explicit `UNSUPPORTED` or `NO_RESULT` if the required semantics remain outside the profile.

Timeout is always `NO_RESULT`.

## Structural discretization work: exact present scope

Implemented files in `fitter-artifact` include:

- `src/clarity/certification/structural_discretization.py`
- `src/clarity/certification/constraint_logic.py`
- `src/clarity/certification/discretization_semantic_validation.py`
- `src/clarity/certification/structural_rule_validation.py`
- `scripts/certify_discretization.py`
- `scripts/validate_symbolic_methods.py`
- `docs/STRUCTURAL_DISCRETIZATION_SAFETY.md`
- `docs/SYMBOLIC_PROCESS_LOGIC.md`

The implemented experimental profile proves a narrow theorem:

- the recognized total functional shield establishes each mapped literal `#Prohibition` or `#Obligation` at completion of the policy-containing action;
- every value retained by that predicate is then held through the quiescent interval before the next policy action.

It recognizes direct policy input bindings, fixed parameters, checked sample copies, controller latches, actuator command effects, Boolean normalization, affine interval contradiction, and bounded exact-rational unit-multiplier Farkas combinations. It returns a positive certificate or `INCONCLUSIVE`; it never reports a negative theorem.

For the Mixing Machine, the theorem is about the literal source requirements over controller-observed levels and actuator states. It does not silently replace a delayed/sampled observation with physical tank level.

The following desired rule is **not implemented**:

```text
available physical safety margin
    >= sound derivative/rate bound × controller discretization interval
```

A future physical-state fast path may extract an affine vector field or Lipschitz bound and discharge that inequality. Until then, a changing physical property that cannot be mapped to held state must pass to another sound proof method.

### Separate validation of proof methods

The symbolic expression representation translates to a small typed constraint logic over Bool, Int, and Real. A logical sequent means premises entail a conclusion; Z3 checks the explicit counterexample formula.

There are deliberately separate programs:

- per-model certification;
- method validation for the reusable proof-rule schemas and their current implementations.

`scripts/validate_symbolic_methods.py` performs the combined method validation. Per-model certification must not rerun that entire suite unless the method or translation changed.

This validates the claimed post-parse logic and reviewed rule implementations. It does not formally verify Python, arbitrary parsing, the SysML frontend, or Z3.

## Continuous-action verification: key conclusion

Continuous action does not inherently require action-space discretization. nuXmv supports real arithmetic, and recognized affine or piecewise-affine relations can be represented symbolically over real-valued actions. The actual difficulty comes from nonlinear dynamics, mode explosion, quantifier structure, unbounded reachability, or an inadequate invariant—not from continuity by itself.

The CLARITY verification theorem is not a proof of trained DNN weights. The proof analyzes the SysML process, constraints, safety properties, action-execution relation, and the NeuralRequirements assumed of the controller. A runtime shield can enforce those NeuralRequirements independently of whether the raw learned proposal complies.

Therefore:

- do not add network-weight verification to this pipeline unless the user separately requests it;
- do not discretize a continuous action space merely because it is continuous;
- compile source-derived real constraints and use structural/algebraic proofs first;
- keep proposed and executed actions distinct so training and verification describe the same architecture.

## Continuous model 1: rotary inverted pendulum

### Source and model scope

Files:

- `sysml-models/rotary-inverted-pendulum/model.sysml`
- `sysml-models/rotary-inverted-pendulum/README.md`
- `sysml-models/rotary-inverted-pendulum/REVIEW.md`

The model is pinned to one sourced QUBE-Servo 2 rotary inverted-pendulum balance process rather than assembled from unrelated examples. Source citations are embedded in comments as nonsemantic provenance.

Controller observations are the measured/estimated arm and pendulum positions and rates plus the reference. The real-valued controller proposal is motor voltage. The amplifier owns physical saturation.

Source requirements:

| Metadata | Requirement |
| --- | --- |
| NeuralRequirement | Neural Balance Controller Soundness |
| Prohibition | Motor Voltage Within Authorized Range |
| Prohibition | Stay Within Balance Controller Envelope |
| Obligation | Controller Supplies State Feedback |

The current NeuralRequirement specifies the exact sourced state-feedback equation. Consequently its shield chooses one exact voltage, not a permissive safe interval. A shielded learned policy is therefore an approximation exercised behind an exact equality shield; it is not an autonomous safe RL controller.

### Why the original nuXmv run was not acceptable

The first generated model had three material problems:

1. a controller command sent directly from an action named `step` was not coupled to the amplifier input;
2. the state-feedback property compared a stored command against sensor values from a different sample time;
3. an auxiliary extractor rule invented nonnegativity for real step targets.

The proof runner also aggregated obligations such that a hard invariant could obscure the status of others.

The fixes couple the direct send, latch the exact observation used with each command, remove the unsound nonnegativity rule, and invoke each invariant independently.

### Hybrid proof

Files:

- `continuous_pipeline.py`
- `symbolic_transition.py`
- `pendulum_envelope_certificate.py`
- `docs/CONTINUOUS_CONTROLLER_PIPELINE.md`
- `docs/PENDULUM_AFFINE_ENVELOPE_CERTIFICATE.md`

The corrected hybrid proof at `d3d72e0dc3f1d522384bce5c13f16f034122d5d9` completed successfully:

- nuXmv: motor-voltage invariant proved;
- exact direct certificate: unbounded balance envelope proved;
- nuXmv: controller state-feedback obligation proved;
- nuXmv: both frozen-target auxiliary invariants proved.

The direct certificate is not a handwritten alternate model. It parses the freshly emitted SMV, requires the recognized amplifier branch, composes the two scan phases, backward-slices irrelevant state, and mechanically builds exact rational `A`, `B`, and `c` for the closed-loop affine recurrence. It proves a finite prefix and an unbounded block contraction, including that the amplifier remains on the assumed interior branch. Unsupported nonlinear policy, changed phase structure, ambiguous actuator branch, or unsupported initial/frozen parameters fails closed.

This is the concrete example of replacing a difficult nuXmv obligation with a lighter source-derived symbolic certificate while leaving the other obligations with nuXmv.

### Pendulum training experiments

The PPO comparison deliberately tested unsafe/unshielded and safe/shielded credit semantics.

A full-horizon experiment at `b50d43a4` used 20 training episodes per mode, 10 evaluation episodes, and a 6,000-step cap:

| Mode | Evaluation successes | Unsafe evaluation episodes | Mean evaluation steps | Interpretation |
| --- | ---: | ---: | ---: | --- |
| Unshielded terminate | 0/10 | 10/10 | 1.0 | Initial proposals violated immediately |
| Unshielded continue | 0/10 | 10/10 | 6,000 | Diverged severely; continuing after unsafe execution gave unusable behavior |
| Shielded executed credit | 10/10 | 0/10 | 1,425.1 | Safe task completion, but the equality shield supplied every executed action |
| Shielded proposal credit | 10/10 | 0/10 | 1,425.1 | Same safe task completion; proposal penalty changed learning signal, not executed behavior |

The later middle configuration removed unshielded-continue, terminated only on actual unshielded Prohibition violation, made override/time costs horizon-normalized, and ensured success reward and punishment were mutually exclusive.

The improvement battery at `d23046ca` compared behavior cloning losses, bounded means, PPO refinements, and a feedforward/no-GRU policy. Every candidate completed 10/10 shielded evaluations, but every candidate had 0/10 unshielded successes and 10/10 unsafe unshielded episodes. The feedforward candidate therefore showed only that the exact shield can make a memoryless proposal network complete the shielded task; it did **not** show that GRU memory is unnecessary for an autonomous policy.

Do not call shielded task success evidence that the learned DNN independently learned the exact safe controller. The unshielded evaluations did not support that claim.

## Continuous model 2: Hall-sensored BLDC motor

### Source and model scope

Files:

- `sysml-models/hall-sensored-bldc/model.sysml`
- `sysml-models/hall-sensored-bldc/README.md`
- `sysml-models/hall-sensored-bldc/REVIEW.md`
- `sysml-models/hall-sensored-bldc/SOURCE_CONFORMANCE_AUDIT.md`

The process is centered on the selected NXP Hall-sensored six-step BLDC material and the compatible Sunrise motor parameter file. Published facts, derived quantities, project assumptions, and excluded behavior are labeled separately. It is a RUN-phase nominal control experiment, not a validated digital twin of the physical bench.

State distinctions include:

- rotor angle, physical speed, and physical energized-pair current;
- sampled Hall sector/code, sampled current, and six-period speed estimate;
- policy proposal, contract-bounded proposal, plant-current-projected duty, and executed phase voltage;
- Hall timing/history and direction;
- fixed motor/bench parameters, target, tolerance, and source-declared assumptions.

Requirements:

| Metadata | Requirement |
| --- | --- |
| NeuralRequirement | Neural Speed Controller Soundness |
| Prohibition | Executed Duty Within Authorized Range |
| Prohibition | Invalid Hall State Disables Drive |
| Prohibition | Valid Hall Commutation Uses Distinct Phases |
| Prohibition | Physical Pair Current Within Rated Limit |
| Prohibition | Projected Pair Current Within Rated Limit |
| Prohibition | Current Safety Projection Remains Feasible |
| Prohibition | Physical Speed Within Nameplate Envelope |
| Obligation | Controller Supplies Bounded Duty Proposal |

Task success is reaching target speed within the project-defined 5 rad/s tolerance. Safety and task completion are distinct.

### Serious defects found and corrected

The initial motor draft and first training runs cannot be treated as current evidence. The following corrections were required:

1. **Speed estimate:** one Hall interval was replaced by the sourced six-period, direction-consistent estimate. Direction reversal resets the period window.
2. **Hall timing:** the executable 50 μs polling approximation and maximum capture delay are explicit; it is not falsely described as exact asynchronous interrupt timing.
3. **Current protection:** the inadequate controller-rate, same-direction cutoff allowed roughly 11 A and was removed. The replacement advances an exact-model observer every 50 μs, algebraically computes the complete safe-duty interval, and projects the bounded proposal onto it.
4. **Target envelope:** the 24 V motor's 9,000 rpm nameplate was incorrectly used as a 12 V task target. The target range is now capped at the exact-part NXP nominal 4,000 rpm; 9,000 rpm remains only the execution safety envelope.
5. **Parser initialization:** Boolean instance initializers were being discarded and are now preserved.
6. **Policy observation:** the `#Completion` input is excluded from pre-action policy observations; it is produced by the execution engine, not available to the controller before acting.
7. **Normalization:** the final trainer uses declared per-input scales rather than one inappropriate global scale.
8. **PPO likelihood:** PPO records the sampled proposal and its log probability. It never scores a projected/executed action as though the policy sampled it.
9. **Reward attribution:** proposal correction is measured against the duty actually executed after the plant-facing current projection, using the completed process state rather than the next policy-input packet.
10. **Floating execution guard:** projection targets `±5.999999 A` so binary64 drift cannot fall a few ulps outside the exact outer `±6 A` runtime requirement. The real-arithmetic proof establishes the stronger inner bound.

The final source still has explicit limitations: scalar averaged two-phase dynamics; assumed pair inductance/reduction; zero external load and loss torque; ideal current sensing; sampled Hall timing; no switching ripple, thermal model, startup/alignment sequence, parameter uncertainty, or hardware trajectory validation.

### Motor verification

`hall_motor_verification.py`:

1. validates a pinned source slice and extracts the exact constants;
2. generates a solver-free structural certificate for observer induction, current-projection algebra, the three projection regions, feasibility over the declared envelope, target feasibility, Hall invalid-state shutdown, and every commutation table row;
3. emits a compact real-arithmetic SMV relation;
4. asks nuXmv to prove each emitted invariant separately.

At `429e7d87efe21164836ec93eebca344122fd5e4f`:

- 36/36 focused runner tests passed;
- all seven nuXmv obligations proved;
- the short guarded Mac MPS PPO smoke completed both shielded modes with zero unsafe executed steps.

These results prove only the encoded nominal discrete model and its stated assumptions. They are not certificates for NXP hardware, unpublished PI tuning, switching-level current peaks, omitted operating phases, or thermal safety.

### Motor PPO semantics and historical evidence

The two active full-training modes are:

- `shielded_executed_credit`: PPO likelihood remains on the proposal, while task reward is based on actual process execution and includes a small intervention cost;
- `shielded_proposal_credit`: PPO likelihood remains on the proposal, and a bounded non-flat penalty replaces ordinary negative reward when the proposal differs from the process-executed action.

No shield intervention terminates an episode. Only an actually allowed unsafe unshielded action may trigger the unshielded safety termination mode.

Historical pre-correction results must not be promoted as current controller evidence. They were useful diagnostics:

- the early 100-episode motor run at `fc642328` had 4/20 shielded-executed evaluation successes and 0/20 shielded-proposal evaluation successes;
- the short ablation at `5f17a507` showed that fixed-target progress reward could produce 10/10 evaluation success, while random-target progress obtained only 2/10; this helped identify target distribution and reward shape as bottlenecks;
- those runs preceded the final plant, parser, observation, PPO-credit, current-projection, and numerical-guard corrections.

## Current motor training jobs — failed experiment record

### Incomplete 2,000-episode request

Request `standalone-motor-full-shielded-20261005-1700` returned exit code **255** after only 110/2,000 episodes of its first mode. It never trained the second mode and produced no final evaluation or comparison. The receipt is `results/standalone-motor-full-shielded-20261005-1700.json` on `compute-results`. Its progress lines are incomplete diagnostics only.

### Misconfigured 500-episode request: discard the result

Request `standalone-motor-500ep-10ms-20261005-1752` was submitted at compute-request commit `ac6d03f86af0d3cee26e317db2c659160d0153e1` against source `429e7d87efe21164836ec93eebca344122fd5e4f`. It requested both shielded modes, 500 training episodes and 100 evaluation episodes per mode, 300 controller decisions per episode, and MacBook MPS.

The user ordered one simple experimental timing change: make the controller discretization/update interval ten times longer and reduce the controller-step count by ten. The submission did **not** implement that as one propagated parameter change. Instead it patched `speedControlTicksPerUpdate` from 20 to 200 while leaving `DT_SECONDS = 0.00005` and the SysML electrical/current/commutation timing separately hardcoded. It also rewrote the safety-slice digest in the temporary runner worktree.

Consequences:

- one nominal 10 ms controller interval still causes 200 interpreted 50 μs engine cycles;
- 300 controller decisions still cost up to 60,000 interpreted SysML transitions per episode;
- 1,000 training episodes plus 200 evaluation episodes request up to 72,000,000 interpreted transitions;
- the small GRU/PPO work may use MPS, but the dominant source interpreter and requirement checks are serial CPU work;
- the tenfold reduction in controller decisions therefore did not produce the intended tenfold reduction in simulation work.

The prior failed request processed roughly 110 episodes in about 31 minutes, implying that the replacement request could require hours or hit the same runner limit. At 18:23 UTC on 2026-10-05, its expected receipt `results/standalone-motor-500ep-10ms-20261005-1752.json` did not exist.

**If this request later returns, record its receipt for provenance and discard its training result. Do not compare, publish, or use its policy checkpoint.** It does not represent the single-parameter timing experiment requested by the user.

The failed response after discovering this problem proposed compiling a fast transition kernel. The user rejected that correctly. No compiler is required or authorized. The defect is the failure to represent and propagate the intended timing parameter consistently.

## Mandatory timing audit and repair — next session only

This is a release blocker, not optional cleanup.

The user uses **`dt` to mean the controller discretization/decision interval**. The demanded experiment should have changed that one parameter from its prior value to a value ten times larger and reduced the controller-step cap by ten. Every dependent timing quantity must be derived from that source or fail closed. Independent timing literals must not be patched by hand.

The next session must first audit, without modifying source:

- the Hall-motor SysML timing declarations and all derived schedules;
- `hall_motor_training.py`, especially `DT_SECONDS`;
- `ContinuousSysMLEnv`, `SimulatorTwin`, and `SimulationEngine` timing semantics;
- controller-update, sensor, shield, plant, observer, and requirement-check cadence;
- episode horizon, controller-step cap, reward normalization, and PPO discount interpretation;
- emitted nuXmv/SMT constants, symbolic recurrences, hashes, certificates, and result metadata;
- the rotary-pendulum model and training path for the same class of duplicated or inconsistent timing.

The audit must produce an explicit dependency table showing the one authoritative controller `dt`, every value derived from it, and every genuinely independent physical timing constant. It must determine whether the intended tenfold controller-`dt` experiment changes only a controller interval, changes the numerical integration interval, or requires another already-specified relationship. Do not invent that relationship privately.

Only after user approval may the next session implement the smallest repair. Required acceptance tests include:

1. change the authoritative controller `dt` once and show every intended dependent value changes automatically;
2. prove that no stale duplicate literal controls runtime or proof behavior;
3. show the physical episode horizon and controller-step count are consistent;
4. show trainer, simulator, shield, symbolic transition, and proof backends report identical timing metadata;
5. fail closed on inconsistent or non-integral timing relationships;
6. rerun focused timing tests before any full verification or training;
7. invalidate all certificates and checkpoints whose timing fingerprint no longer matches.

Do not add a compiler, simulator replacement, macro-transition engine, or performance architecture unless the user separately authorizes it after the minimal parameter repair is understood.

## Other design conclusions from this session

### Shielded training and task performance

A shield guarantees only its safety contract. It can distort exploration and credit by replacing proposals, especially when multiple safe actions exist and the task-optimal safe policy occupies a narrow subset. Executed-action reward, proposal penalty, and unshielded safety termination are different training semantics and must remain explicit.

For the pendulum equality shield, the shield itself determines the task action; successful shielded episodes reveal little about raw-policy competence. For permissive interval/polytope shields, shielded PPO may meaningfully learn among safe actions, but intervention and proposal-error statistics remain necessary.

### Noise

No noisy model was implemented in this branch. The agreed conceptual boundary is:

- bounded-support disturbances can enter a universal proof as explicit nondeterministic bounds;
- unbounded Gaussian noise makes an absolute finite safety claim false unless a shield or physical bottleneck bounds the safety-relevant effect;
- otherwise the claim must become probabilistic/confidence-qualified.

Do not silently truncate Gaussian noise and retain an absolute theorem.

### Model selection criteria

A future continuous model must be based on:

1. one authoritative device specification;
2. one authoritative accepted engineering/scientific model;
3. or measured data identifying an actual process.

Compatible sources may enrich missing fields only when compatibility is explicit and documented. The Hall motor and pendulum source comments record their selected references; preserve them as nonsemantic provenance.

## Compute resources

The workflow has three compute levels:

- browser-session VM: editing and lightweight tests; package/hardware limitations;
- GitHub-hosted resources: ordinary CI and symbolic jobs where supported;
- personal runners: automatic external execution, with MacBook MPS for PyTorch and smaller workers for routine jobs.

The personal runner communicates only through GitHub request/result branches. Pin every request to a source commit, record resource requirements, and inspect result JSON plus output/error tails. Elapsed time or a missing file is not a verdict.

## Immediate new-session checklist

1. Treat both continuous-action models as quarantined and do not present their results externally.
2. Check whether the misconfigured 500-episode request returned; archive its receipt but discard its model/checkpoint result.
3. Do not rerun either long motor job.
4. Perform the read-only timing audit described above for the motor and pendulum paths.
5. Produce the timing dependency table and identify every duplicate or independently hardcoded value.
6. Report the smallest proposed repair to the user and wait for explicit approval.
7. Do not introduce a compiler or other architectural expansion.
8. After approval, test timing components individually before running complete verification.
9. Reassess every prior continuous-model proof and training claim against the repaired timing fingerprint.
10. Keep continuous-action Markov generalization separate unless explicitly authorized.

## Soundness and reporting boundaries

- A property constrains transition behavior only when the selected semantic profile says it does; a requirement must not silently become an assumption.
- Physical and sampled values remain distinct unless the source explicitly relates them.
- Proposed, shielded, and plant-executed actions remain distinct.
- Fixed context is shared between paired histories but is not automatically controller-visible.
- A structural refusal is inconclusive, not a counterexample.
- Z3 or nuXmv timeout is inconclusive.
- Bounded simulation can expose bugs and witnesses; it cannot prove an unbounded universal theorem.
- Source hashes detect drift but do not prove the reviewed source interpretation correct.
- Every certificate must record source identity, proof profile, exact timing, assumptions, scope, non-claims, and backend result.
- No claim extends beyond the encoded SysML model and its explicit assumptions.
