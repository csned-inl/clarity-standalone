# Hall-sensored brushless motor: pinned NXP RUN-phase model

This directory contains a SysML v2 model in the same CLARITY-oriented form as
the standalone thermostat, cruise-controller, mixing-machine, and rotary
inverted-pendulum models. It is not an average of several motors or reference
applications.

## Model identity and authority

The modeled process is NXP's Hall-sensored six-step control arrangement for the
Sunrise `42BLY3A78-24110` motor on the NXP low-voltage motor-control bench.
The source family is:

- NXP, *S32M244 - Hall sensor based 6-step BLDC motor control*:
  <https://community.nxp.com/t5/S32M-Knowledge-Base/S32M244-Hall-sensor-based-6-step-BLDC-motor-control/ta-p/2013453>
- NXP, *BLDC/PMSM Low Voltage Motor Control Accessory Kit*:
  <https://www.nxp.com/design/design-center/development-boards-and-designs/BLDC-KIT>
- NXP Application Code Hub, exact Sunrise motor parameter file:
  <https://github.com/nxp-appcodehub/an-mc-pmsm-foc-2sh-s32k344/blob/main/FreeMASTER_control/MCAT/param_files/M1_params_Sunrise95.txt>
- NXP application note AN12435, *3-Phase Sensorless BLDC Motor Control Kit
  with S32K144*, which the S32M244 reference itself cites for the two-conducting-
  phase six-step motor abstraction:
  <https://www.nxp.com/docs/en/application-note/AN12435.pdf>

The parameter file belongs to a different NXP control application, but it names
the exact same motor part. This model imports only intrinsic motor data from
that file: pole pairs, resistance, d/q inductances, back-EMF constant, torque
constant, inertia, and rated phase current. It does **not** import that other
application's controller gains, voltage thresholds, thermal thresholds, or
speed envelope.

## Exact scope

`model.sysml` represents the post-alignment RUN phase of the unloaded rotor-disc
bench. This is analogous to the pendulum model's deliberate restriction to its
balance phase. The model includes:

- continuous mechanical angle, mechanical speed, and energized-pair current;
- a six-sector quotient/remainder representation of physical electrical angle;
- distinct sampled Hall, current, and Hall-derived speed state;
- the exact Sunrise Hall sequence `110, 100, 101, 001, 011, 010`;
- NXP's exact clockwise and counterclockwise phase switching table;
- a continuous signed PWM-duty proposal and a separately executed duty;
- a 50 microsecond commutation/current-sampling step and a 1 millisecond speed
  policy update (20 commutation ticks);
- 12 V bench supply context, kept distinct from the motor's 24 V nameplate;
- invalid-Hall shutdown, duty saturation, and measured-current intervention;
- a non-unique neural policy contract over the continuous action; and
- explicit task target and completion tolerance as project scenario data.

The two-phase electrical relation uses the q-axis inductance as the
torque-channel inductance and represents two conducting phases plus one
disconnected phase. This is an explicit control-oriented reduction. It does not
pretend to be a phase-resolved finite-element motor model.

## State separation

The following are intentionally different symbols:

- physical sector versus sampled Hall code;
- physical speed versus Hall-event speed estimate;
- physical energized-pair current versus sampled current;
- policy-proposed duty versus bounded proposal versus executed duty; and
- motor nameplate voltage versus the actual bench DC-bus voltage.

Collapsing any of these pairs would erase delay, quantization, or execution
semantics and could make a later Markov or safety certificate unsound.

## Continuous action and shield boundary

The policy proposes any real signed duty fraction. Its neural requirement
restricts issued proposals to `[-1, 1]` and requires zero duty for an invalid
Hall code. The drive separately implements the physical execution boundary:
it saturates out-of-range proposals, blocks same-direction voltage at the
measured current limit, disables on invalid Hall state, and selects the exact
phase tuple for the current Hall code and direction.

This separation permits the same downstream pipeline to study an unshielded
policy that already satisfies the neural requirement or a shielded policy that
is projected onto it. The commutated drive remains part of the plant interface
in either case.

## Timing and discretization

The S32M244 reference specifies a 50 microsecond current sampling period and a
1 millisecond speed-control period. The model's executable realization uses
forward Euler for the continuous averaged plant at 50 microseconds. At the
9000 rpm nameplate speed with two pole pairs, one step moves about 0.0943
electrical radians, well below the `pi/3` sector width, so at most one Hall
boundary can be crossed per step inside the declared envelope.

Forward Euler and the atomic Hall-event realization are project implementation
choices. They require a separate discretization certificate; they are not
represented as equations copied verbatim from NXP.

## Deliberate exclusions

- INIT, current-sensor calibration, alignment, START, STOP, and fault-clear
  sequencing;
- a thermal plant, winding-temperature estimate, or temperature trip value;
- an invented friction coefficient, drag curve, or external-load model;
- transistor dead time, switching ripple, and individual MOSFET dynamics;
- phase-resolved magnetic saturation, cogging, and torque ripple;
- an imported PI controller or gains from a different NXP board/application;
- stochastic Hall/current noise; and
- a claim that the scalar averaged electrical relation is a complete digital
  twin of every winding transient.

These are omissions, not zeros silently asserted as sourced physical facts.
Adding any of them requires an explicit source-backed extension or a separately
identified model.

## Current status

The first draft parses with the standalone SysML parser, preserves all required
state distinctions, and exposes the exact commutation table and source
constants for regression tests. Full simulation, formal extraction, action
shielding, training, and nuXmv support are later pipeline stages and are not
claimed merely because this source model parses.

