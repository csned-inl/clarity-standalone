# E001 — analytic policy to generic Structured Text

**State:** active experiment, not an architecture decision

## Question

Can the existing, SysML-derived analytic policy be translated into a small,
deterministic IEC 61131-3 Structured Text function block while retaining enough
provenance to support later semantic comparison and PLC compilation tests?

## Scope

The experiment translates only the pure Boolean/affine rule language currently
written by `analytic.py`:

- Boolean literals and output references;
- `not`, `and`, and `or`;
- affine comparisons using `<`, `<=`, `>`, or `>=`;
- acyclic dependencies among Boolean outputs.

It does not translate the plant, device state machines, Modbus exchanges,
runtime shield, GRU policy, scenario generator, or complete SysML model.

## Inputs and checks

The generator accepts a SysML model and analytic `policy.json`. Before emitting
code it checks:

1. the policy kind;
2. the model SHA-256 recorded by the policy;
3. exact input/output name agreement with the model's `#Neural` action;
4. supported source and target types;
5. valid, case-insensitively unique ST identifiers;
6. rule completeness, valid references, finite coefficients, and acyclic
   output dependencies.

## Initial type policy

| SysML type | Experimental ST type | Status |
|---|---|---|
| `Boolean` | `BOOL` | automatic |
| `Real` | `LREAL` | automatic; cross-runtime numeric equivalence unproved |
| `Integer` | caller-selected `SINT`/`INT`/`DINT`/`LINT` | explicit choice required |

The generator refuses to silently map unbounded SysML `Integer` to a bounded PLC
integer. E001 may use `DINT` for the mixing example, but that is an experiment
parameter rather than a project-wide decision.

Integer-only affine rules remain integer expressions and therefore also require
a later range/overflow argument. Rules that mix integer and real inputs are
currently rejected rather than assigned an implicit conversion policy.

## Generated artifact

The output is a generic `FUNCTION_BLOCK` with `VAR_INPUT`, `VAR_OUTPUT`, and one
assignment per output in dependency order. A deterministic JSON manifest records
the input hashes, type mapping, output hash, assumptions, and non-claims.

## Evidence levels

| Level | E001 status |
|---|---|
| Deterministic translation and provenance | implemented here |
| Unit tests over all three current model interfaces | implemented here |
| Source-policy versus emitted-expression differential tests | initial Python-level checks only |
| Parse/compile with an independent IEC 61131-3 tool | next |
| Execute compiled controller against CLARITY scenarios | next |
| Demonstrate scan/numeric semantic correspondence | open |
| Vendor-specific import and execution | open |
| LD generation | out of scope for E001 |

## Success criterion

E001 succeeds as a research probe if it produces reviewable ST, rejects
ambiguous or unsupported mappings, and identifies the next semantic gaps. It
does not succeed merely because a PLC tool accepts the text.
