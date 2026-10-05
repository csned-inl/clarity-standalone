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
| Current sample period | NXP S32M244 Hall reference | `50 microseconds` |
| Speed action period | NXP S32M244 Hall reference | `1 millisecond` |
| Plant realization | CLARITY model design | two-conducting-phase averaged electrical relation and forward Euler |
| Target/tolerance | CLARITY scenario design | explicit scenario input and completion tolerance, not motor specifications |

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
  item connections, two physical flows, one actuator state machine, and four
  requirements with the standalone parser.
- Confirmed the proposal state machine partitions all real duty proposals into
  above-range, below-range, and in-range cases.
- Confirmed physical sector/current/speed and sampled Hall/current/speed use
  distinct state symbols.
- Checked all six CCW and all six CW rows against NXP's Sunrise table.
- Checked `20 * 0.00005 = 0.001` for the two documented rates.
- Checked the maximum nameplate-speed electrical increment is below one Hall
  sector per commutation sample.
- Kept 24 V nameplate, 12 V bench supply, and continuous normalized duty as
  different model concepts.

## Claims not yet made

The initial checks do not prove the reduced electrical dynamics reproduce raw
bench trajectories, that forward Euler preserves every continuous invariant,
that the current intervention alone proves a 6 A physical-current invariant,
or that the generated controller is safe. Those require separate tests and
certificates. In particular, “same-direction voltage is inhibited at the
sampled current boundary” is the encoded property; it is not silently promoted
to a stronger continuous-time current theorem.

