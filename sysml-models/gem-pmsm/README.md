# GEM PMSM speed benchmark

See the [current work record](../../docs/PMSM_WORK_LOG.md) for the latest
checker implementation, trial results, and deferred Flow* evaluation.

The complete register of changes from the authoritative GEM benchmark, including
the active 1-ms profile and added training, shield, proof, and pipeline behavior,
is in [SPEC_DEVIATIONS.md](SPEC_DEVIATIONS.md).

Authoritative benchmark: `Cont-SC-PMSM-v0`, upb-lea/gym-electric-motor commit
`b474daf9cf1ef55e9161009cb06bb996072d0df0`.

`SOURCE_TRACEABILITY.csv` records the physical/electrical parameters, converter,
solver, load, observation timestamps/scales, reward, seeded references and sampled
current monitor. The author code supplies the plant specification; no controller
gains, hard tracking tolerance, deadline or physical stop sequence is invented.

The project-selected completion horizon is three seconds (30,000 control intervals).
The `done` input is true on the final decision, whose response is integrated and
checked before terminal success. A violating final response is failure.

`gem_pmsm_runtime.py` evaluates the model calculations and supplies the declared
SciPy/NumPy services. `gem_pmsm_adapter.py` implements the sampled CLARITY protocol.
The adapter rejects changes to the supported scheduler rather than executing a
different action graph silently. It is a narrow, explicit native backend, not a
general-purpose SysML execution engine.

The pipeline supports runtime tests and experimental PPO. It emits a
source-derived SMV relation and checks a conditional shield-interface contract;
full numerical-runtime and trained-policy safety verification remain unproved.
See the root README for commands.
