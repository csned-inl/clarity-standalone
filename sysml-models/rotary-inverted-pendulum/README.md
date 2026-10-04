# QUBE-Servo 2 rotary inverted-pendulum model

This directory contains a first-stage SysML v2 source model written in the
same CLARITY-oriented style as the standalone thermostat, cruise-controller,
and mixing-machine models.

## Exact scope

`model.sysml` represents the **balance phase** of a Quanser QUBE-Servo 2
rotary inverted pendulum about the upright equilibrium. It does not yet model
the nonlinear swing-up controller. That limitation is intentional: the first
continuous-action model uses a source-backed linear transition relation that
was exercised against physical QUBE-Servo 2 hardware instead of inventing a
partially specified swing-up implementation.

The source model includes:

- four continuous physical state variables;
- distinct sampled encoder and filtered-velocity state;
- a continuous proposed motor voltage;
- an explicit amplifier execution relation that zeros or clamps the proposal;
- a source-backed LQR state-feedback controller contract;
- initialization and scenario constraints;
- voltage, fault-response, and upright-envelope requirements; and
- explicit completion tolerances.

The completion tolerances are declared model-design values, not manufacturer
limits. The physical transition coefficients, controller gains, capture
envelope, velocity-filter cutoff, and voltage range are traceable below.

## Sources and conventions

1. T. Rasanen and V.-P. Pyrhonen, *State feedback control of a rotary inverted
   pendulum*, Finnish Society of Automation, 2019:
   <https://www.automaatioseura.fi/site/assets/files/2398/procap2352_rasanenpyrhonen.pdf>

   Used for the upright linear state-space coefficients, the LQR gain
   `[-3.8730, 51.2299, -2.2650, 4.3458]` applied as negative state feedback,
   the `50 s/(s+50)` velocity-estimator
   transfer function, the +/-15 V controller restriction, and the +/-20 degree
   upright balance envelope. The paper reports simulation and physical-device
   experiments on the QUBE-Servo 2.

2. Quanser, *QUBE-Servo 2 Product Information Sheet v1.0*:
   <https://www.quanser.com/wp-content/uploads/2017/03/QUBE_Servo_2_Product_Info_Sheet_v1.0.pdf>

   Used to identify the physical platform, its DC motor, optical encoders,
   amplifier, integrated current/tachometer sensing, and pendulum module.

3. Quanser QUBE-Servo 2 QUARC device documentation:
   <https://docs.quanser.com/quarc/documentation/qube_servo2_usb.html>

   Used to cross-check the continuous voltage channel, encoder channels,
   amplifier enable, and diagnostic fault/stall inputs.

The paper defines the hardware pendulum encoder's zero at the downward
position, but linearizes about 180 degrees. This SysML model stores the
physical pendulum coordinate as **deviation from upright**, so zero denotes the
upright equilibrium. The convention is explicit and is not a sensor/physical
state collapse: physical and sampled values remain separate symbols.

## Deliberate exclusions

- nonlinear swing-up dynamics and energy-shaping control;
- encoder-count quantization;
- stochastic measurement noise;
- a quantitative thermal/current model;
- stall-warning timing semantics; and
- a manufacturer-certified rotary-arm travel limit.

These features must not be inferred from this model. They require explicit
source-backed extensions. In particular, the model's +/-20 degree condition is
the balance-controller envelope, not a general claim that other pendulum
angles are mechanically unsafe.

## Pipeline status

This is currently a source-model prototype. The standalone parser, simulator,
SMV extractor, and policy code still assume parts of the older Boolean-action
profile. Adding the file does not imply that those tools already support its
real-valued policy output or continuous execution relation.
