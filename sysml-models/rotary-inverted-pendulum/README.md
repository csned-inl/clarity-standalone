# Rotary inverted pendulum: pinned balance experiment

This directory contains a SysML v2 model in the same CLARITY-oriented form as
the standalone thermostat, cruise-controller, and mixing-machine models. It is
not a composite of several inverted-pendulum models.

## Model identity and authority

The process is pinned to the balance experiment in:

- T. Rasanen and V.-P. Pyrhonen, *State feedback control of a rotary inverted
  pendulum*, Finnish Society of Automation, 2019:
  <https://www.automaatioseura.fi/site/assets/files/2398/procap2352_rasanenpyrhonen.pdf>

That paper is the authority for the modeled plant and controller. In
particular, `model.sysml` uses its state convention, published rounded
state-space coefficients (equation 24), `50 s/(s+50)` velocity estimator
(equation 27), LQR weights and gain (equations 31-32), 1 ms angle-measurement
period, +/-20 degree balance envelope, zero-state balance initialization, and
90-degree reference-tracking experiment.

Other QUBE courseware publishes materially different matrices and gains. Those
numbers describe different identified or configured processes and are
intentionally **not** imported here. A different QUBE plant must be a separate
model with a separate identity.

The following manufacturer documents are used only for complementary hardware
facts about the same QUBE-Servo 2 platform, not to replace the paper's plant or
controller:

- Quanser, *QUBE-Servo 2 Product Information Sheet v1.0*:
  <https://www.quanser.com/wp-content/uploads/2017/03/QUBE_Servo_2_Product_Info_Sheet_v1.0.pdf>
- Quanser, *QUBE-Servo 2 User Manual*, v1.0, 2016 (archived copy):
  <https://manuals.plus/m/ec3a4b23ac24cda93b3b79da157bec38b85cd363bd2365b4ebc718ad27be92a5>
  The manual specifies a +/-10 V recommended motor/load-output range, +/-15 V
  maximum amplifier range, 2 A peak current, 0.5 A continuous current, and a
  prolonged-stall warning.
- Quanser QUARC QUBE-Servo 2 device documentation:
  <https://docs.quanser.com/quarc/documentation/qube_servo2_usb.html>

The hardware manual distinguishes a recommended +/-10 V output range from an
absolute +/-15 V amplifier range and separately cautions that motor input is at
most +/-10 V. The model therefore projects the executed motor voltage to
+/-10 V. The paper's 90-degree experiment reaches only about 6.5 V, so this
hardware restriction does not alter the centered experiment.

## Exact scope

`model.sysml` represents only the linear balance phase about the upright
equilibrium. It includes:

- four continuous physical states in the paper's state order;
- distinct sampled angle and filtered-velocity states;
- the paper's full-state LQR relation as the `#NeuralRequirement` contract;
- a continuous proposed motor-voltage action;
- a message-triggered amplifier execution relation with +/-10 V saturation and
  held voltage between samples;
- a fixed 1 ms sample period;
- a 90-degree-or-smaller arm reference scenario;
- voltage, balance-envelope, and controller-response requirements; and
- explicit project-defined task-completion tolerances.

The policy output is subject to the neural requirement in the same way as the
three reference models: a CLARITY shield may enforce that relation, while an
unshielded deployment assumes the policy already satisfies it. The downstream
amplifier saturation is physical action execution, not a substitute for that
policy shield.

## Coordinate and feedback conventions

The paper's encoder angle is zero in the downward position and is linearized at
180 degrees. This model stores `pendulumAngleFromUprightRadians`, so zero is the
upright equilibrium. This is a coordinate transform, not a merger of physical
and sensor state.

The paper prints `u = Kx` in one place but gives the closed-loop matrix as
`A-BK`, and the listed LQR gain is the conventional MATLAB gain used with
negative feedback. The model therefore implements `u = -K(x-xr)`. With the
published rounded matrices this sign produces a stable closed-loop matrix; the
opposite sign produces an unstable positive-real pole.

## Sampling and execution semantics

The continuous plant relation is the source relation. The executable sampled
model makes two additional, explicit project choices:

- forward Euler for the plant; and
- backward Euler for the `50 s/(s+50)` velocity estimator.

Both use `samplePeriodSeconds = 0.001`. These are not presented as equations
copied from Quanser. They are the declared implementation contract whose
discretization safety must be certified separately.

Within one sample, the held executed voltage advances the plant, the encoder
samples the new physical state, the controller emits a command, and the
amplifier records the bounded voltage for the next plant update. Sensor values
are sent through a `connect` item channel; continuous physical and drive values
use `flow`, matching the reference models and current CLARITY runtime semantics.

## Source-backed validation observations

A deterministic runtime smoke test using the source LQR law, the declared
Euler realizations, and a +90 degree arm target produced:

- maximum pendulum deviation: about 8.19 degrees;
- maximum executed voltage: about 6.08 V; and
- convergence of the arm to the target with the pendulum returning upright.

The paper reports approximately 8 degrees and +/-6.5 V for that experiment.
This agreement is a useful transcription and execution-order check; it is not
a formal proof and is not represented as physical validation of every model
detail.

## Deliberate exclusions

- nonlinear swing-up and energy-shaping control;
- encoder-count quantization and stochastic measurement noise;
- a quantitative current/thermal model and the three-second stall timer;
- unmodeled device-to-device parameter variation;
- a mechanical rotary-arm travel constraint; and
- a claim that the paper's rounded linear model exactly reproduces hardware.

The paper itself says its physical Simulink implementation contains a relative
angle compensation term absent from its simulation relation and that the model
does not describe the physical pendulum exactly. Accordingly, this file is a
traceable model of the published balance experiment, not a manufacturer-
certified digital twin.

The +/-20 degree requirement is the balance-controller envelope, not a general
mechanical safety boundary. If swing-up, current/thermal safety, quantization,
or another QUBE identification is added, it must be introduced as an explicit
extension or separate model with its own sources and verification obligations.

## Pipeline status

The SysML source parses and executes under the current standalone parser and
simulator. The older SMV extractor and policy tooling still assume Boolean
action outputs in important paths. This model therefore does not claim that
the existing end-to-end nuXmv or training pipeline already supports its
real-valued action without extension.
