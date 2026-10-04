# Rotary inverted-pendulum model review record

This record states what was checked before treating the SysML file as a
defensible source-model draft. It is intentionally separate from a future
formal certificate.

## Acceptance rule

The model centers one process: the 2019 Rasanen-Pyrhonen QUBE-Servo 2 balance
experiment. Values from other QUBE workbooks are not blended into it. A second
identified plant is a second SysML model.

## Reference-to-model map

| Model element | Authority | Encoded value or rule |
|---|---|---|
| State order and upright linear relation | 2019 paper, eq. 24 | `[arm angle, upright-angle deviation, arm rate, pendulum rate]`; published rounded `A` and `B` |
| Velocity estimates | 2019 paper, eq. 27 | `50 s/(s+50)`; backward-Euler realization is explicitly project-defined |
| Controller | 2019 paper, eqs. 31-32 | `K=[-3.8730, 51.2299, -2.2650, 4.3458]`, applied as `u=-K(x-xr)` |
| Measurement period | 2019 paper, hardware description | 0.001 s |
| Balance envelope | 2019 paper, controller requirement | +/-20 degrees from upright while healthy balance control is active |
| Reference experiment | 2019 paper, sec. 5 | initial zero state; arm reference up to +/-pi/2 by symmetry of the encoded linear process |
| Motor/load voltage | QUBE-Servo 2 hardware manual | executed voltage clamped to +/-10 V |
| Completion tolerances | CLARITY model design | declared as project choices, not source safety limits |

The paper reports rounded physical parameters, a rounded `A,B` realization,
and a gain computed from an unprinted higher-precision realization. Recomputing
`A,B` from the rounded parameter table or recomputing LQR from the rounded
matrix does not reproduce every printed digit. This model therefore treats the
paper's printed equation 24 and equation 32 as the process definition; it does
not silently substitute a newly recomputed hybrid.

## Defects removed from the first draft

1. The first draft treated the +/-15 V command-channel range as the safe motor
   range. The motor/load limit is +/-10 V.
2. The sensor item was connected as a continuous `flow` and never entered the
   controller mailbox. It now uses explicit item `send` and `connect` semantics.
3. The amplifier used an action-body `accept` that silently reused zero when no
   message was present. It is now an item-triggered state machine that holds its
   last executed voltage.
4. The initial sensor history could disagree with the physical initial state.
   Both now begin at the source experiment's zero state.
5. Arbitrary initial velocities were previously allowed inside an angle-only
   envelope. The centered experiment now uses the source's upright-rest initial
   condition rather than making an unsupported invariant claim.
6. The requirement name incorrectly called +/-20 degrees a certified region.
   It is now identified as the balance-controller envelope.
7. Documentation overstated the paper's linear relation as a hardware-validated
   digital twin. The paper's own modeling caveat and compensation term are now
   recorded.
8. The sample period and numerical integration choices were implicit. They are
   now explicit model/implementation data.

## Checks performed

- Parsed package, part instances, item connections, state machine, scenario
  values, and all three requirements with the standalone parser.
- Confirmed sampled and physical variables remain different state symbols.
- Confirmed each sensor send reaches and is consumed by the controller.
- Confirmed proposed commands reach the amplifier and that its three guards are
  exhaustive and mutually exclusive over real commands.
- Exercised in-range, high, and low amplifier cases, including both boundaries.
- Checked that `A-BK` is stable for the published rounded matrix and that
  `A+BK` is not, supporting the chosen feedback sign.
- Simulated the centered +90 degree experiment for five seconds at 1 ms and
  compared peak voltage and pendulum deflection with the paper.
- Confirmed the three declared requirements remain true in that smoke test.

## What these checks do not prove

They do not prove the parser implements all SysML v2 semantics, the numerical
scheme preserves continuous-time safety, the linearization is globally valid,
or the physical device exactly matches the model. Those are separate assurance
claims. In particular, the smoke test is a regression check and must never be
reported as a formal safety proof.
