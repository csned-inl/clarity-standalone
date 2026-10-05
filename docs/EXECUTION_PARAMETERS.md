# Source-owned execution parameters

Pipeline-wide execution settings are declared in `model.sysml`, not in Python
runners. A declaration has a primitive type and the `#ExecutionParameter`
metadata marker:

```sysml
#ExecutionParameter attribute controllerIntervalSeconds : Real = 0.001;
#ExecutionParameter attribute integrationSubstepsPerControllerInterval : Integer = 20;
```

`sysml-models/execution_parameters.py` loads every marked value, preserves its
type, rejects duplicate names, and produces a deterministic fingerprint. The
common timing contract derives

```text
integration_step_seconds = controllerIntervalSeconds
                           / integrationSubstepsPerControllerInterval
```

The simulator, SMV extractor, formal verifier, discrete and continuous
training entry points, diagnostic runners, and result metadata all consume
that derived step. An explicitly supplied `dt` is accepted only as a backward-
compatible assertion; a disagreement with the source fails closed.

## Changing timing

- To make both controller decisions and plant integration ten times less
  frequent, change only `controllerIntervalSeconds` and keep the substep count
  unchanged.
- To make controller decisions ten times less frequent while preserving the
  plant integration step, change `controllerIntervalSeconds` and the substep
  count by the same factor.
- To refine only plant integration between decisions, change only the substep
  count.

These edits alter execution behavior; they do not by themselves prove that a
previous safety or accuracy result remains valid. New reports carry the source
values, derived intervals, and fingerprint so results cannot silently mix
configurations.

Compute requests should pin the source commit and may additionally pin this
fingerprint before launching expensive work:

```bash
python3 sysml-models/execution_parameters.py path/to/model.sysml \
  --expect-fingerprint EXPECTED_SHA256
```

Runner commands must not patch timing literals or rewrite a safety-slice digest
in their temporary checkout. A timing experiment is a source commit containing
the SysML parameter edit; the request executes that commit and archives the
reported execution-parameter block with the result.

## Parameters beyond timing

The loader is deliberately generic. Additional `Real`, `Integer`, or `Boolean`
execution parameters are included in the immutable value map and fingerprint.
A downstream consumer can require one typed name through `require_decimal()`,
`require_integer()`, or `require_boolean()` rather than creating another runner
constant. Timing is the first shared contract built on this mechanism, not a
special-purpose parser limitation.
