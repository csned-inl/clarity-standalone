# Hall-sensored BLDC model review record

This record separates source transcription checks from later verification and
physical-validation claims.

## Acceptance rule

The model centers one process: NXP's Hall-sensored six-step RUN-phase example
for the Sunrise `42BLY3A78-24110` on the NXP low-voltage rotor-disc bench.
Intrinsic data for that exact motor may be taken from NXP's exact-part
parameter file. Controller and protection settings from a different board are
not transferable merely because they use the same motor.

## Reference-to-model map

| Model element | Authority | Encoded value or rule |
|---|---|---|
| Motor identity | NXP BLDC_KIT | Sunrise `42BLY3A78-24110` |
| Nameplate | NXP BLDC_KIT | 24 V, 95 W, 9000 rpm, 6 A, 2 pole pairs |
| Bench supply | NXP BLDC_KIT | 12 VDC, 5 A supply |
| Mechanical setup | NXP BLDC_KIT | framed motor with rotor disc; no added external load modeled |
| Resistance | NXP exact-part parameter file | `0.192 ohm` |
| d/q inductance | NXP exact-part parameter file | `96/107 microhenry` |
| Back-EMF constant | NXP exact-part parameter file | `0.005872 V s/rad` |
| Torque constant | NXP exact-part parameter file | `0.010614 N m/A` |
| Inertia | NXP exact-part parameter file | `1.2e-5 kg m^2` |
| Hall sequence | NXP S32M244 Hall reference | `110,100,101,001,011,010` by increasing sector |
| Phase switching | NXP S32M244 Hall reference | all 12 direction/Hall phase tuples copied directly |
| Hall resolution | NXP S32M244 Hall reference | one sector per 60 electrical degrees |
| Commutation update | NXP S32M244 Hall reference | phase tuple changes atomically at Hall event; double-buffer internals abstracted |
| Speed estimate | NXP S32M244 Hall reference | actual speed calculated from all six most recent commutation periods |
| Hall timing | NXP S32M244 Hall reference | asynchronous GPIO interrupt; executable 50 us polling is an explicit project assumption |
| Current sample period | NXP S32M244 Hall reference | `50 microseconds` |
| Speed/current action period | NXP S32M244 Hall reference | both controller functions execute every `1 millisecond` |
| Current limiting | NXP S32M244 Hall reference versus CLARITY model design | source uses two PI outputs and synchronized integrators; executable model uses an explicitly non-equivalent 50 us exact-model duty projection because exact gains/state are unavailable |
| Numerical current guard | CLARITY execution design | projection uses a 5.999999 A inner interval to preserve the exact 6 A requirement under binary64 evaluation |
| Plant realization | CLARITY model design | nominal scalar two-conducting-phase relation, explicit effective coefficients, zero-load/zero-loss profile, and forward Euler |
| Target envelope | NXP exact-part parameter profile | symmetric target capped at published `N_nom=4000 rpm`; 9000 rpm remains nameplate safety envelope |
| Completion tolerance | CLARITY scenario design | 5 rad/s project-defined completion threshold |

## Compatibility judgment

NXP's S32M244 Hall article directly names the Sunrise motor and the BLDC_KIT
page directly names both the motor and the compatible S32M2 setup. NXP's
parameter file also names the exact motor. Reusing intrinsic motor constants is
therefore a same-part identification, not numerical averaging. The file's FOC
controller gains, application voltage limits, and protection thresholds are
not imported because those are implementation-specific rather than intrinsic
motor properties.

## Initial checks

- Parsed the package, five part definitions, four system part instances, three
  item connections, two physical flows, one actuator state machine, and eight
  requirements with the standalone parser.
- Confirmed the proposal state machine partitions all real duty proposals into
  above-range, below-range, and in-range cases.
- Confirmed physical sector/current/speed and sampled Hall/current/speed use
  distinct state symbols.
- Checked all six CCW and all six CW rows against NXP's Sunrise table.
- Checked `20 * 0.00005 = 0.001` for the two documented rates.
- Replaced the incorrect one-period speed estimate with the documented sum of
  the six most recent commutation periods.
- Removed the unsafe 1 ms memoryless cutoff and added a 50 microsecond
  exact-model projection derived from the encoded electrical recurrence. The
  replacement is deliberately identified as a CLARITY filter and is not
  represented as NXP's dual-PI algorithm.
- Checked plant/observer equality by source-shape validation and executable
  induction, all three projection regions algebraically, interval feasibility
  over the declared envelope, and 12,000 adversarial reversal steps.
- Made the pair-level electrical coefficients, effective torque constant,
  effective bench inertia, external load, loss torque, Hall-capture delay, and
  current-measurement error explicit assumptions instead of hidden constants.
- Checked the maximum nameplate-speed electrical increment is below one Hall
  sector per commutation sample.
- Kept 24 V nameplate, 12 V bench supply, and continuous normalized duty as
  different model concepts.

## Claims not yet made

The checks prove the 6 A current invariant of the encoded discrete recurrence;
they do not prove that the reduced electrical dynamics reproduce raw bench
trajectories, that forward Euler preserves an unmodeled continuous-time
waveform invariant, or that the hardware remains within 6 A under parameter
error and switching ripple. The policy contract, exact-model filter, and Hall
relation are separate assumptions/guarantees rather than a claim that the
generated neural controller itself implements NXP's PI firmware.

The nominal Hall generator cannot emit `000` or `111`, so the closed nominal
model's invalid-Hall implication is vacuous. The drive relation handles an
invalid input correctly at its boundary, but a hardware fault-coverage claim
requires a separate fault-injection environment that can actually produce
those codes.

See `SOURCE_CONFORMANCE_AUDIT.md` for the impact of every material unsupported
quantity and the boundary of claims that remain defensible.
