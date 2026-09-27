# CLARITY PLC extension

**Status:** exploratory implementation baseline  
**Updated:** 2026-09-27

## Purpose

Extend the existing CLARITY assurance chain toward IEC 61131-3 controller
artifacts, initially Structured Text (ST) and later potentially Ladder Diagram
(LD). This file is the compact project hub; it is not a claim that a final
translation architecture has been selected.

## What is inherited and observed

`clarity-standalone` currently provides a reproducible chain for three SysML v2
models:

1. parse the project-specific SysML v2 subset;
2. extract SMV and check emitted properties with nuXmv;
3. derive a specification shield and identify dead Boolean actions;
4. produce either an analytic predicate policy or a GRU policy;
5. evaluate the shielded controller in the SysML simulator; and
6. publish a final policy only after the configured zero-violation gates pass.

The analytic and GRU paths, CUDA execution, and sanitized workstation reporting
have been exercised in the current project. See `README.md` and
`WORKSTATION_REPORTING.md` for operational details.

## What remains open

- whether PLC generation is direct from SysML or uses one or more explicit
  intermediate representations;
- which SysML v2 subset and execution semantics form the supported source
  language;
- whether ST, LD, or both are primary targets;
- PLC task, scan, initialization, numeric, I/O, and fault semantics;
- generic IEC 61131-3 versus a selected vendor dialect and toolchain;
- how generated code is compiled, executed, and compared with the source
  model;
- what evidence supports semantic preservation through code generation and the
  vendor compiler;
- whether any natural-language or other specification layer precedes SysML.

SIS-specific restrictions remain a separate concern from general PLC support.
No safety certification claim follows merely from emitting IEC 61131-3 text.

## Working organization

| Location | Role |
|---|---|
| `sysml-models/` | Existing SysML models, parser, simulator, and SMV extractor |
| `analytic.py`, `gru.py`, `rl/` | Existing policy construction and assurance gates |
| `plc/` | Experimental PLC backends and semantic adapters |
| `docs/plc/` | Experiment records, assumptions, and unresolved decisions |
| `tests/` | Regression and cross-representation checks |
| `runs/` | Generated evidence and local execution artifacts; not source |

## Source map

| Material | Use in this project |
|---|---|
| `CLAIRTY-v0.20(3).pdf` | Funding-level CLARITY vision and proposed PLC extension; not an implementation specification |
| `plc-languages-sis-clarity-summary(3).pdf` | PLC language and standards orientation; separates general PLC work from SIS constraints |
| `COMPUTE_RESOURCES_HANDOFF.md` | Hosted-VM/workstation capabilities and execution boundary |
| `INL_Codex_Zscaler_conversation_transcript.txt` | Historical access diagnosis; not part of the technical architecture |
| this repository and `SOURCE_MANIFEST.json` | Current implementation evidence for the inherited CLARITY chain |

The earlier external `project_context/` notes are incorporated here. Source
documents remain outside this repository; this map locates their roles without
copying them into the codebase.

## Working principle

Maintain the sequence **source/direction -> question -> candidate -> explicit
decision -> reproducible experiment -> evidence**. Experiments may implement a
candidate before it is selected, but their assumptions and non-claims must stay
visible. Reported proposal claims, observed test results, and future assurance
claims are not interchangeable.

## Current experiment

`E001` tests one candidate backend boundary:

```text
SysML #NeuralRequirement
        -> CLARITY analytic policy JSON
        -> deterministic generic Structured Text function block
```

This path is a deliberately narrow experiment, not the selected project
architecture. It is useful because the policy JSON already records source-model
hashes, inputs, outputs, Boolean dependencies, and affine predicates. The
experiment can therefore expose PLC typing, evaluation-order, numeric, and
toolchain questions without first inventing another representation.

See [`docs/plc/E001_STRUCTURED_TEXT.md`](docs/plc/E001_STRUCTURED_TEXT.md).

## Assurance boundary

The current nuXmv result concerns the extracted CLARITY model. Simulator tests
concern the Python execution path. Neither currently proves that generated ST,
a vendor compiler, a PLC runtime, or physical I/O preserves those semantics.
Every PLC experiment must keep those evidence layers distinct.
