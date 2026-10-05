# Pendulum affine envelope certificate

This document applies only to `csned-inl/clarity-standalone` branch
`codex/pendulum-controller-pipeline`. It does not modify or reinterpret the
repository's original three controller models.

## Purpose

nuXmv proves four of the corrected pendulum model's five invariant
obligations quickly, but the bare physical-angle envelope makes IC3 attempt to
discover a high-dimensional reachable-state invariant and times out. The
affine fast path supplies that missing induction argument directly.

## Trusted transition source

The certifier does not contain a handwritten plant matrix. The proof path is:

1. `mc-extract.py` emits the real-valued SMV transition system from SysML.
2. `symbolic_transition.py` parses that exact emitted transition relation.
3. It requires the amplifier delivery event at phase 1, chooses the declared
   interior amplifier branch as a proof assumption, composes phases 0 and 1,
   and rejects unsupported or nonlinear expressions.
4. Backward dependency slicing retains exactly the state capable of
   influencing physical pendulum angle or executed voltage.
5. The resulting `AffineTransitionSystem` compiles mechanically to exact
   rational matrices `A`, `B`, and `c` for `x' = A*x + B*r + c`.

The certificate report records the SHA-256 of the complete SMV source. Any
change to SysML or extraction therefore produces a different proof subject.
Unsupported phase structure, missing frozen-parameter bounds, nonlinear
products, nonconstant initial state, or ambiguous actuator branches fail
closed.

## Unbounded proof

For this model, `c = 0`, the initial dynamic state is zero, and the one frozen
target parameter `r` lies in the source interval
`[-1.570796326795, 1.570796326795]`. Exact Gaussian elimination obtains the
parameter-dependent equilibrium `E*r`, and the error satisfies `e' = A*e`
while the amplifier stays in its interior branch.

The checker establishes with exact `Fraction` arithmetic:

- prefix length: 2,600 complete physical cycles;
- prefix maximum physical pendulum angle: less than `0.151016` radians;
- prefix maximum executed voltage: less than `6.083695` volts;
- block length: 2,000 complete physical cycles;
- infinity norm of `A^2000`: less than `0.289`;
- tail physical-angle bound, including every point inside a block: less than
  `0.048645` radians;
- tail voltage bound, including both block endpoints: less than `7.910186`
  volts.

The source safety limit is `0.349065850399` radians and the amplifier limit is
10 volts. The voltage bounds prove that the assumed interior amplifier branch
is the branch actually executed for the prefix and every future contraction
block. Therefore the recurrence is the reachable clamped-system recurrence,
not an uncontrolled linearization. Strict block contraction repeats the tail
argument indefinitely.

## Aggregation and refusal behavior

`formal.py` accepts a named direct certifier for an obligation. In the
continuous pendulum pipeline only `Stay Within Balance Controller Envelope`
uses this path. nuXmv still checks the motor-voltage requirement, the feedback
requirement, and the two frozen-target auxiliaries in independent processes.
Overall verification succeeds only when the analytical certificate and every
nuXmv obligation report `proved`.

This method is deliberately incomplete. It does not claim support for noise,
multiple frozen parameters, nonzero affine offsets, nonzero initial dynamic
state, nonlinear dynamics, or multiple reachable actuator modes. Such a model
is rejected by this fast path and requires another sound proof method.
