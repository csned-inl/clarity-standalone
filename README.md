# CLARITY standalone reference pipeline

This directory is a self-contained copy of the SysML v2 controller pipeline:

1. Parse one of the corrected SysML v2 models and generate an SMV model.
2. Run nuXmv IC3 on every emitted invariant. Stop if extraction or proof fails.
3. Build the specification shield and identify structurally dead actions.
4. Build a policy by one of two methods:
   - `analytic`: derive affine threshold predicates and Boolean output rules
     directly from the SysML `#NeuralRequirement`; no gradient training.
   - `gru`: use the original 64-unit GRU actor critic, oracle cloning, and
     2,000 PPO episodes. Save a checkpoint every 100 episodes.
5. Run the controller with the shield in the SysML simulator. For GRU, keep
   only checkpoints with zero requirement violations and zero evaluation
   errors; rank by fewest safety violations, then fewest unsuccessful episodes,
   then lowest shield override rate. Recheck the winner on separate scenarios
   before publishing. No final policy is published unless its safety count is zero.

Safety is checked at completed initialization and every completed simulator
cycle. Recorded failures and evaluation errors are retained until the next
policy call. A completion observation still requires its final controller
response to execute and pass those checks before the episode succeeds.

The run output contains `formal/model.smv`, `formal/nuxmv.txt`,
`formal/verification.json`, `shield.json`, and evaluation results. The only
published policy is under `final/`: `policy.json` for the analytical path or
`policy.pt` for GRU. Files under `training/full/`, including `best.pt` and
`final.pt`, are intermediate checkpoints. If no checkpoint passes the final
gate, the run stops without a `final/policy.pt`.

## Run

Requires Python 3.10+, PyTorch, NumPy, and a nuXmv executable. Install the
Python packages with `python -m pip install -r requirements.txt` in a virtual
environment.

```bash
python pipeline.py --model thermostat --mode analytic --output runs --nuxmv /path/to/nuXmv
python pipeline.py --model mixing --mode gru --output runs --nuxmv /path/to/nuXmv
```

`--model` accepts `thermostat`, `cruise`, `mixing`, or `all`. Each run writes
to `<output>/<model>/<mode>` and requires that directory to be new, so a
failed run cannot leave an old final policy in place. The default GRU run
uses 2,000 oracle samples, 100 cloning epochs, 2,000 PPO episodes, 100
checkpoint evaluation episodes, and 100 held-out evaluation episodes.

Each model owns its execution timing through typed `#ExecutionParameter`
attributes. `controllerIntervalSeconds` declares the policy decision interval;
`integrationSubstepsPerControllerInterval` derives the plant integration step.
The pipeline loads those values once and propagates their immutable fingerprint
through formal extraction, simulation, training, checkpoint evaluation,
selection, and reports. A legacy `--dt` argument is only a consistency
assertion and fails if it conflicts with the SysML source.

The same loader retains every typed `#ExecutionParameter`, so solver budgets,
diagnostic switches, or other pipeline-wide settings can use the same
source-owned mechanism without adding another independent runner constant.

Mixing scan timing uses `sysml-models/scan_clock.py`. It bounds binary64 error
after each actual clock increment and subtraction, adapting to the timestep
and scan period. Comparisons outside that bound use the native clock values;
uncertain comparisons use exact arithmetic on the helper's recorded clock
history. The SysML files and model variable types remain unchanged. No fixed
epsilon or assumed maximum episode length is used. The SMV translation keeps
the scan period's real division and reads the clock after its source increment,
including when copying the last-scan time.

For non-default diagnostics, the CLI also exposes `--seed`, `--max-steps`,
`--eval-episodes`, `--test-episodes`, `--oracle-samples`, `--oracle-epochs`,
and `--ppo-episodes`. PPO episodes must be a multiple of 100.

## Source of the isolated components

- The three `sysml-models/*/model.sysml` files are copies of the corrected
  models in `fitter_artifact/src/clarity/models` in the automated-writing
  project. The mixing model includes the subsequently applied 2 mL
  conservative controller tolerance; the other models are from local commit
  `6d17efb`.
- `sysml-models/sysml_parser.py` is copied from the current
  `fitter_artifact/src/clarity/sysml/parser.py`. It handles the SysML v2
  expression precedence used by those corrected specifications.
- The SMV extractor, simulator, specification shield,
  GRU network, oracle cloning, PPO, and environment come from the earlier
  `shield-pipeline-new-sysml` backup. The copied code lives in
  `sysml-models/` and `rl/` here. The shield now compiles the parsed requirement
  into ordinary Python predicates. Both policy modes check the original
  observations without sigmoid approximations or float32 conversion. If no
  valid action exists, or evaluating the requirement fails, execution errors.
  Negative scenario bounds are read from the parsed unary-minus expressions.
- `formal.py`, `analytic.py`, `gru.py`, `selection.py`, and `pipeline.py`
  connect these pieces and enforce the final gate.
- The existing runtime timing repair from the current project is ported into
  the legacy simulator, adapter, environment, and evaluation consumers.
  `parser_values.py` restores declared starting values; `requirement_events.py`
  carries completed-cycle results. Derived sensor aliases remain live until
  read, as in the repaired runtime. Neither helper imports the proof extensions.

Run the response-timing regression tests with
`python tests/test_response_timing.py -v`.
Run the scan timing and precision regressions with
`python tests/test_scan_clock.py -v`.

This reference contains no MDP proof, discretization proof, architecture
fitting, or continuous cruise controller pipeline.
