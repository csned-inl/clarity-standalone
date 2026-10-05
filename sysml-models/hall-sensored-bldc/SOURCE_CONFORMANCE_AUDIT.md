# Source-conformance and missing-data audit

This audit distinguishes four categories that must not be conflated:

1. **directly sourced** facts copied from the selected NXP material;
2. **derived** values obtained by a stated calculation from sourced facts;
3. **model assumptions** needed to make a deterministic executable profile;
4. **excluded behavior** for which this model makes no claim.

The model is a traceable RUN-phase control experiment. It is not yet a
validated digital twin of the physical bench.

## Findings that required correction

### Speed estimation

NXP states that actual speed is calculated from all six most recent
commutation periods. The earlier draft used only the latest period. That could
change feedback delay and ripple substantially and could make controller
training, Markov analysis, and transient comparisons describe the wrong
process. The model now keeps six intervals and computes the signed mechanical
speed only once a complete direction-consistent window exists.

The public article does not say how interval history is treated across a
direction reversal. Averaging intervals from opposite directions is physically
wrong, so the executable profile resets the window on inferred direction
change. That reset is an explicit project boundary, not a transcription claim.

### Hall timing

NXP captures Hall changes with asynchronous GPIO interrupts and measures the
interval with a timer. The standalone executable runtime advances all
components on one 50 microsecond clock, so it can observe a sector transition
up to one clock late. The model exposes `maximumHallCaptureDelaySeconds =
0.00005` rather than calling the polling semantics exact.

This matters because timestamp quantization perturbs the six-period speed
estimate, delays commutation, and changes controller observations. Any theorem
that depends on exact asynchronous event timing needs a separate bounded-delay
or event-driven model. The current profile can support only claims conditional
on the declared capture-delay approximation.

### Current limiting

NXP executes a speed PI and current-limit PI in the 1 ms interrupt, compares
their duty outputs, and synchronizes their integrators. The earlier draft used
a memoryless same-direction cutoff at the 1 ms controller boundary. That
cutoff oscillated between full duty and zero, let the encoded physical current
rise to roughly 11 A, and was neither the NXP algorithm nor a valid 6 A safety
mechanism. It has been removed.

The replacement is a CLARITY exact-model safety filter, not a reconstruction of
the unavailable NXP gains. At every 50 microsecond plant step it:

1. advances an observer using the plant's exact initial state, previous
   executed duty, coefficients, and forward-Euler recurrence;
2. solves the electrical recurrence algebraically for the full duty interval
   that makes the next pair current lie in `[-6 A, 6 A]`; and
3. projects the bounded policy proposal onto that interval, or shuts down if
   the interval is infeasible.

Induction establishes observer/plant equality for the encoded transition, and
substitution establishes the one-step current invariant. An adversarial
12,000-step reversal test exercises the executable relation independently.
The certificate also checks interval feasibility over the declared current and
speed envelope. These facts prove the model's discrete pair-current property;
they do not reproduce PI response, establish robustness to parameter error, or
bound unmodeled switching ripple in hardware.

The exact reference controller still requires its configured threshold, PI
gains, numerical scaling, saturation behavior, integrator initial state, and
integrator synchronization semantics.

### Target envelope

The motor's 9000 rpm value is a 24 V nameplate maximum, not a justified 12 V
training target. The exact-part NXP parameter profile separately gives
`N_nom=4000 rpm` and `N_max=5500 rpm`. The scenario target is now capped at the
published nominal 4000 rpm (`418.879020... rad/s`); the 9000 rpm nameplate is
retained only as the execution safety envelope. The 5 rad/s completion
tolerance remains project-defined and is identified as such.

## Assumption-impact register

| Missing or reduced quantity | Executable replacement | Impact if wrong | Permitted claim |
|---|---|---|---|
| Pair electrical dynamics | `Rpair=2R`, `Lpair=2Lq`, `Kepair=2Ke` | changes current rise, back-EMF cancellation, phase lag, and peak current | only the declared nominal scalar plant |
| Six-step torque conversion | exact-part `Kt` used as effective pair-current coefficient | changes acceleration and equilibrium torque; FOC `Kt` need not be the exact six-step average coefficient | conditional nominal mechanical response |
| Complete bench inertia | exact-part listed inertia used as effective bench inertia | an omitted rotor disc/coupler inertia makes acceleration too fast and controller tuning optimistic | no hardware rise-time claim |
| Friction, windage, cogging | zero loss torque | removes damping and parasitic torque; changes equilibrium speed, coast-down, current, and training reward | zero-loss nominal profile only |
| External load | zero load torque | makes acceleration/task completion optimistic and removes disturbance rejection | unloaded declared scenario only |
| PWM switching and phase ripple | averaged pair voltage | hides switching peaks, torque ripple, diode/freewheel behavior, and dead time | no switching-level voltage/current theorem |
| Current sensing | physical pair current plus fixed zero error | omits ADC quantization, amplifier offset, filter dynamics, and active-PWM sampling geometry | ideal-measurement profile only |
| Hall capture | 50 us polling bound | delays commutation and perturbs speed timestamps | bounded-delay sampled profile only |
| Current controller | 50 us exact-model predictive projection | differs from NXP PI dynamics and is sensitive to every encoded coefficient | discrete encoded pair-current invariant only |
| Thermal state | excluded | current-safe-looking traces may still overheat the winding or inverter | no thermal claim |
| Startup/alignment/stop/reversal sequence | excluded; RUN begins aligned | hides high startup current and transition faults | RUN-phase claim only |
| Hall and power-stage faults | nominal Hall generator plus drive invalid-code branch | invalid-code requirement is vacuous in the closed nominal model | boundary behavior, not fault coverage |
| Raw bench trajectories | unavailable | numerical resemblance cannot be measured and parameter errors remain unidentified | no empirical fidelity claim |

## Source-supported core that remains intact

- selected Sunrise `42BLY3A78-24110` identity and published nameplate facts;
- exact-part intrinsic parameter values, kept separate from the Hall
  application's controller configuration;
- six 60-electrical-degree sectors;
- the published Sunrise Hall sequence and all direction/phase table rows;
- two energized phases and one disconnected phase in six-step operation;
- asynchronous Hall-event architecture represented with an explicit bounded
  polling approximation;
- six-period speed-estimation structure;
- 1 ms neural proposal timing and 50 us plant/current-filter timing; and
- separation of physical state, sampled state, proposed command, limited
  command, and executed drive command.

## Certificate boundary

A certificate generated from this file is sound only for the transition system
actually encoded, including every `#ModelAssumption`. It must identify the
model/source digest and assumption profile. Its 6 A statement is about the
encoded forward-Euler pair current. It must not be described as a certificate for the NXP hardware, reference firmware, switching-level phase-current peaks,
parameter uncertainty, or omitted operating phases.

The next fidelity upgrade should replace one assumption at a time with either
source-backed data or measured identification and then rerun both the structural
and semantic validation. Unsupported values must never be silently tuned until
the smoke trajectory looks plausible.
