package RotaryInvertedPendulum {
    private import ScalarValues::*;

    // CLARITY annotations used by the three standalone reference models.
    metadata def Neural;
    metadata def NeuralRequirement;
    metadata def Prohibition;
    metadata def Obligation;
    metadata def Termination;
    metadata def ScenarioInput;
    metadata def ScenarioConstraint;

    // This model is the balance-phase abstraction of the particular
    // QUBE-Servo 2 experiment documented by Rasanen and Pyrhonen (2019).
    // It deliberately does not claim to model swing-up or every QUBE revision.
    // Physical state, sampled sensor state, proposed voltage, and executed
    // voltage are distinct symbols.

    item def PendulumPhysicalState {
        attribute armAngleRadians : Real;
        attribute pendulumAngleFromUprightRadians : Real;
        attribute armAngularVelocityRadiansPerSecond : Real;
        attribute pendulumAngularVelocityRadiansPerSecond : Real;
    }

    port def PendulumPhysicalStatePort {
        in item state : PendulumPhysicalState;
    }

    item def PendulumReading {
        attribute armAngleRadians : Real;
        attribute pendulumAngleFromUprightRadians : Real;
        attribute estimatedArmAngularVelocityRadiansPerSecond : Real;
        attribute estimatedPendulumAngularVelocityRadiansPerSecond : Real;
    }

    port def PendulumSensorPort {
        in item reading : PendulumReading;
    }

    item def MotorVoltageCommand {
        attribute volts : Real;
    }

    port def MotorVoltageCommandPort {
        in item command : MotorVoltageCommand;
    }

    item def StateDerivative {
        attribute armAngleRate : Real;
        attribute pendulumAngleRate : Real;
        attribute armAngularAcceleration : Real;
        attribute pendulumAngularAcceleration : Real;
    }

    part def RotaryPendulumPlant {
        // Physical state. Pendulum angle is zero at the upright equilibrium.
        attribute armAngleRadians : Real;
        attribute pendulumAngleFromUprightRadians : Real;
        attribute armAngularVelocityRadiansPerSecond : Real;
        attribute pendulumAngularVelocityRadiansPerSecond : Real;

        // Linearized QUBE-Servo 2 state-space coefficients about upright.
        // State order: arm angle, pendulum angle, arm rate, pendulum rate.
        attribute armAccelerationFromPendulum : Real;
        attribute armAccelerationFromArmRate : Real;
        attribute armAccelerationFromPendulumRate : Real;
        attribute armAccelerationFromVoltage : Real;
        attribute pendulumAccelerationFromPendulum : Real;
        attribute pendulumAccelerationFromArmRate : Real;
        attribute pendulumAccelerationFromPendulumRate : Real;
        attribute pendulumAccelerationFromVoltage : Real;
        attribute samplePeriodSeconds : Real;

        port motorVoltagePort : MotorVoltageCommandPort;
        port physicalStatePort : ~PendulumPhysicalStatePort;

        action step {
            in dt : Real;

            item derivative : StateDerivative;
            assign derivative.armAngleRate := armAngularVelocityRadiansPerSecond;
            assign derivative.pendulumAngleRate := pendulumAngularVelocityRadiansPerSecond;
            assign derivative.armAngularAcceleration :=
                armAccelerationFromPendulum * pendulumAngleFromUprightRadians +
                armAccelerationFromArmRate * armAngularVelocityRadiansPerSecond +
                armAccelerationFromPendulumRate * pendulumAngularVelocityRadiansPerSecond +
                armAccelerationFromVoltage * motorVoltagePort.command.volts;
            assign derivative.pendulumAngularAcceleration :=
                pendulumAccelerationFromPendulum * pendulumAngleFromUprightRadians +
                pendulumAccelerationFromArmRate * armAngularVelocityRadiansPerSecond +
                pendulumAccelerationFromPendulumRate * pendulumAngularVelocityRadiansPerSecond +
                pendulumAccelerationFromVoltage * motorVoltagePort.command.volts;

            // Project-defined forward-Euler realization of the documented
            // continuous model at the declared fixed sample period. All four
            // updates use the derivative snapshot above.
            #ContinuousRate assign armAngleRadians :=
                armAngleRadians + derivative.armAngleRate * samplePeriodSeconds;
            #ContinuousRate assign pendulumAngleFromUprightRadians :=
                pendulumAngleFromUprightRadians +
                derivative.pendulumAngleRate * samplePeriodSeconds;
            #ContinuousRate assign armAngularVelocityRadiansPerSecond :=
                armAngularVelocityRadiansPerSecond +
                derivative.armAngularAcceleration * samplePeriodSeconds;
            #ContinuousRate assign pendulumAngularVelocityRadiansPerSecond :=
                pendulumAngularVelocityRadiansPerSecond +
                derivative.pendulumAngularAcceleration * samplePeriodSeconds;
        }

        bind physicalStatePort.state.armAngleRadians = armAngleRadians;
        bind physicalStatePort.state.pendulumAngleFromUprightRadians =
            pendulumAngleFromUprightRadians;
        bind physicalStatePort.state.armAngularVelocityRadiansPerSecond =
            armAngularVelocityRadiansPerSecond;
        bind physicalStatePort.state.pendulumAngularVelocityRadiansPerSecond =
            pendulumAngularVelocityRadiansPerSecond;
    }

    part def EncoderAndVelocityEstimator {
        // Sampled values are intentionally distinct from physical values.
        attribute sampledArmAngleRadians : Real;
        attribute sampledPendulumAngleFromUprightRadians : Real;
        attribute previousArmAngleRadians : Real;
        attribute previousPendulumAngleFromUprightRadians : Real;
        attribute estimatedArmAngularVelocityRadiansPerSecond : Real;
        attribute estimatedPendulumAngularVelocityRadiansPerSecond : Real;
        attribute velocityFilterCutoffRadiansPerSecond : Real;
        attribute samplePeriodSeconds : Real;

        port plantPort : PendulumPhysicalStatePort;
        port upstreamPort : ~PendulumSensorPort;

        action step {
            in dt : Real;

            // Project-defined backward-Euler realization of the documented
            // H(s) = w*s/(s+w) estimator.
            assign estimatedArmAngularVelocityRadiansPerSecond :=
                (estimatedArmAngularVelocityRadiansPerSecond +
                 velocityFilterCutoffRadiansPerSecond *
                 (plantPort.state.armAngleRadians - previousArmAngleRadians)) /
                (1.0 + velocityFilterCutoffRadiansPerSecond * samplePeriodSeconds);
            assign estimatedPendulumAngularVelocityRadiansPerSecond :=
                (estimatedPendulumAngularVelocityRadiansPerSecond +
                 velocityFilterCutoffRadiansPerSecond *
                 (plantPort.state.pendulumAngleFromUprightRadians -
                  previousPendulumAngleFromUprightRadians)) /
                (1.0 + velocityFilterCutoffRadiansPerSecond * samplePeriodSeconds);

            assign sampledArmAngleRadians := plantPort.state.armAngleRadians;
            assign sampledPendulumAngleFromUprightRadians :=
                plantPort.state.pendulumAngleFromUprightRadians;
            assign previousArmAngleRadians := plantPort.state.armAngleRadians;
            assign previousPendulumAngleFromUprightRadians :=
                plantPort.state.pendulumAngleFromUprightRadians;

            item reading : PendulumReading;
            assign reading.armAngleRadians := sampledArmAngleRadians;
            assign reading.pendulumAngleFromUprightRadians :=
                sampledPendulumAngleFromUprightRadians;
            assign reading.estimatedArmAngularVelocityRadiansPerSecond :=
                estimatedArmAngularVelocityRadiansPerSecond;
            assign reading.estimatedPendulumAngularVelocityRadiansPerSecond :=
                estimatedPendulumAngularVelocityRadiansPerSecond;
            send reading via upstreamPort;
        }
    }

    part def MotorAmplifier {
        attribute maximumVoltageMagnitude : Real;
        attribute proposedVoltage : Real;
        attribute executedVoltage : Real;

        port proposalPort : MotorVoltageCommandPort;
        port drivePort : ~MotorVoltageCommandPort;

        // The command transition mirrors the item-triggered actuator pattern
        // used by the three standalone CLARITY reference models. The held
        // executed voltage is applied by the plant during the next sample.
        state def AmplifierBehavior {
            entry; then waiting;
            state waiting;

            transition above_motor_limit
                first waiting
                accept proposal : MotorVoltageCommand via proposalPort
                if proposal.volts > maximumVoltageMagnitude
                do action {
                    assign proposedVoltage := proposal.volts;
                    assign executedVoltage := maximumVoltageMagnitude;
                }
                then waiting;

            transition below_motor_limit
                first waiting
                accept proposal : MotorVoltageCommand via proposalPort
                if proposal.volts < 0.0 - maximumVoltageMagnitude
                do action {
                    assign proposedVoltage := proposal.volts;
                    assign executedVoltage := 0.0 - maximumVoltageMagnitude;
                }
                then waiting;

            transition inside_motor_limit
                first waiting
                accept proposal : MotorVoltageCommand via proposalPort
                if proposal.volts <= maximumVoltageMagnitude and
                   proposal.volts >= 0.0 - maximumVoltageMagnitude
                do action {
                    assign proposedVoltage := proposal.volts;
                    assign executedVoltage := proposal.volts;
                }
                then waiting;
        }

        exhibit state amplifierBehavior : AmplifierBehavior;

        bind drivePort.command.volts = executedVoltage;
    }

    part def BalanceController {
        attribute targetArmAngleRadians : Real;
        attribute captureAngleRadians : Real;
        attribute completionArmAngleToleranceRadians : Real;
        attribute completionPendulumAngleToleranceRadians : Real;
        attribute completionAngularVelocityToleranceRadiansPerSecond : Real;
        attribute armAngleGain : Real;
        attribute pendulumAngleGain : Real;
        attribute armAngularVelocityGain : Real;
        attribute pendulumAngularVelocityGain : Real;

        attribute lastProposedVoltage : Real;

        port sensorPort : PendulumSensorPort;
        port proposalPort : ~MotorVoltageCommandPort;

        #Neural action def Policy {
            in armAngleRadians : Real;
            in pendulumAngleFromUprightRadians : Real;
            in estimatedArmAngularVelocityRadiansPerSecond : Real;
            in estimatedPendulumAngularVelocityRadiansPerSecond : Real;
            in targetArmAngleRadians : Real;
            #Completion in done : Boolean;

            out proposedMotorVoltage : Real;
        }

        #NeuralRequirement requirement def 'Neural Balance Controller Soundness' {
            subject p : Policy;

            // The equality is the paper's LQR law, interpreted using the
            // conventional u = -K(x-xr) sign that yields A-BK. The amplifier
            // independently owns the hardware voltage projection.
            require constraint {
                p.proposedMotorVoltage ==
                    0.0 -
                    (armAngleGain *
                        (p.armAngleRadians - p.targetArmAngleRadians) +
                     pendulumAngleGain *
                        p.pendulumAngleFromUprightRadians +
                     armAngularVelocityGain *
                        p.estimatedArmAngularVelocityRadiansPerSecond +
                     pendulumAngularVelocityGain *
                        p.estimatedPendulumAngularVelocityRadiansPerSecond)
            }
        }

        action step {
            in dt : Real;

            item reading : PendulumReading;
            accept reading : PendulumReading via sensorPort.reading;

            action policyCall : Policy {
                in armAngleRadians := reading.armAngleRadians;
                in pendulumAngleFromUprightRadians :=
                    reading.pendulumAngleFromUprightRadians;
                in estimatedArmAngularVelocityRadiansPerSecond :=
                    reading.estimatedArmAngularVelocityRadiansPerSecond;
                in estimatedPendulumAngularVelocityRadiansPerSecond :=
                    reading.estimatedPendulumAngularVelocityRadiansPerSecond;
                in targetArmAngleRadians := targetArmAngleRadians;
                in done :=
                    reading.armAngleRadians >=
                        targetArmAngleRadians - completionArmAngleToleranceRadians and
                    reading.armAngleRadians <=
                        targetArmAngleRadians + completionArmAngleToleranceRadians and
                    reading.pendulumAngleFromUprightRadians >=
                        0.0 - completionPendulumAngleToleranceRadians and
                    reading.pendulumAngleFromUprightRadians <=
                        completionPendulumAngleToleranceRadians and
                    reading.estimatedArmAngularVelocityRadiansPerSecond >=
                        0.0 - completionAngularVelocityToleranceRadiansPerSecond and
                    reading.estimatedArmAngularVelocityRadiansPerSecond <=
                        completionAngularVelocityToleranceRadiansPerSecond and
                    reading.estimatedPendulumAngularVelocityRadiansPerSecond >=
                        0.0 - completionAngularVelocityToleranceRadiansPerSecond and
                    reading.estimatedPendulumAngularVelocityRadiansPerSecond <=
                        completionAngularVelocityToleranceRadiansPerSecond;
            }

            assign lastProposedVoltage := policyCall.proposedMotorVoltage;
            item command : MotorVoltageCommand;
            assign command.volts := policyCall.proposedMotorVoltage;
            send command via proposalPort;
        }
    }

    part def RotaryInvertedPendulumSystem {
        part plant : RotaryPendulumPlant;
        part encoder : EncoderAndVelocityEstimator;
        part amplifier : MotorAmplifier;
        part controller : BalanceController;

        flow from plant.physicalStatePort to encoder.plantPort;
        connect encoder.upstreamPort to controller.sensorPort;
        connect controller.proposalPort to amplifier.proposalPort;
        flow from amplifier.drivePort to plant.motorVoltagePort;

        attribute currentTimeSeconds : Real = 0.0;
        attribute samplePeriodSeconds : Real = 0.001;

        action step {
            in dt : Real;
            #ContinuousRate assign currentTimeSeconds :=
                currentTimeSeconds + samplePeriodSeconds;
        }

        #Prohibition
        requirement def 'Motor Voltage Within Authorized Range' {
            doc /* The voltage actually executed by the amplifier shall remain within its configured range. */
            subject s : RotaryInvertedPendulumSystem;
            require constraint {
                s.amplifier.executedVoltage >=
                    0.0 - s.amplifier.maximumVoltageMagnitude and
                s.amplifier.executedVoltage <=
                    s.amplifier.maximumVoltageMagnitude
            }
        }

        #Prohibition
        requirement def 'Stay Within Balance Controller Envelope' {
            doc /* During balance operation, the physical pendulum shall remain within the source experiment's configured upright envelope. */
            subject s : RotaryInvertedPendulumSystem;
            require constraint {
                s.plant.pendulumAngleFromUprightRadians >=
                        0.0 - s.controller.captureAngleRadians and
                s.plant.pendulumAngleFromUprightRadians <=
                        s.controller.captureAngleRadians
            }
        }

        #Obligation
        requirement def 'Controller Supplies State Feedback' {
            doc /* The controller shall issue the specified state-feedback command. */
            subject s : RotaryInvertedPendulumSystem;
            require constraint {
                s.currentTimeSeconds > 0.0
                    implies s.controller.lastProposedVoltage ==
                        0.0 -
                        (s.controller.armAngleGain *
                            (s.encoder.sampledArmAngleRadians -
                             s.controller.targetArmAngleRadians) +
                         s.controller.pendulumAngleGain *
                            s.encoder.sampledPendulumAngleFromUprightRadians +
                         s.controller.armAngularVelocityGain *
                            s.encoder.estimatedArmAngularVelocityRadiansPerSecond +
                         s.controller.pendulumAngularVelocityGain *
                            s.encoder.estimatedPendulumAngularVelocityRadiansPerSecond)
            }
        }
    }

    part system : RotaryInvertedPendulumSystem {
        part :>> plant {
            // The source experiment's balance trial begins at upright rest.
            attribute :>> armAngleRadians = 0.0;
            attribute :>> pendulumAngleFromUprightRadians = 0.0;
            attribute :>> armAngularVelocityRadiansPerSecond = 0.0;
            attribute :>> pendulumAngularVelocityRadiansPerSecond = 0.0;

            attribute :>> armAccelerationFromPendulum = -41.6;
            attribute :>> armAccelerationFromArmRate = -4.16;
            attribute :>> armAccelerationFromPendulumRate = 1.37;
            attribute :>> armAccelerationFromVoltage = 13.9;
            attribute :>> pendulumAccelerationFromPendulum = 72.4;
            attribute :>> pendulumAccelerationFromArmRate = -4.11;
            attribute :>> pendulumAccelerationFromPendulumRate = -2.40;
            attribute :>> pendulumAccelerationFromVoltage = 13.7;
            attribute :>> samplePeriodSeconds = 0.001;
        }

        part :>> encoder {
            attribute :>> sampledArmAngleRadians = 0.0;
            attribute :>> sampledPendulumAngleFromUprightRadians = 0.0;
            attribute :>> previousArmAngleRadians = 0.0;
            attribute :>> previousPendulumAngleFromUprightRadians = 0.0;
            attribute :>> estimatedArmAngularVelocityRadiansPerSecond = 0.0;
            attribute :>> estimatedPendulumAngularVelocityRadiansPerSecond = 0.0;
            attribute :>> velocityFilterCutoffRadiansPerSecond = 50.0;
            attribute :>> samplePeriodSeconds = 0.001;
        }

        part :>> amplifier {
            attribute :>> maximumVoltageMagnitude = 10.0;
            attribute :>> proposedVoltage = 0.0;
            attribute :>> executedVoltage = 0.0;
        }

        part :>> controller {
            #ScenarioInput attribute :>> targetArmAngleRadians = 0.0;
            attribute :>> captureAngleRadians = 0.349065850399;
            attribute :>> completionArmAngleToleranceRadians = 0.017453292520;
            attribute :>> completionPendulumAngleToleranceRadians = 0.017453292520;
            attribute :>> completionAngularVelocityToleranceRadiansPerSecond = 0.05;
            attribute :>> armAngleGain = -3.8730;
            attribute :>> pendulumAngleGain = 51.2299;
            attribute :>> armAngularVelocityGain = -2.2650;
            attribute :>> pendulumAngularVelocityGain = 4.3458;
            attribute :>> lastProposedVoltage = 0.0;
        }

        #ScenarioConstraint constraint scenarioConstraints {
            controller.targetArmAngleRadians >= -1.570796326795 and
            controller.targetArmAngleRadians <= 1.570796326795 and
            plant.samplePeriodSeconds == samplePeriodSeconds and
            encoder.samplePeriodSeconds == samplePeriodSeconds
        }
    }
}
