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

    // This first model covers the QUBE-Servo 2 balance phase about the
    // upright equilibrium. It deliberately does not claim to model swing-up.
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

    item def AmplifierStatus {
        attribute enabled : Boolean;
        attribute faulted : Boolean;
        attribute proposedVoltage : Real;
        attribute executedVoltage : Real;
    }

    port def AmplifierStatusPort {
        in item status : AmplifierStatus;
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

            // Forward-Euler realization of the documented continuous model.
            // All four updates use the derivative snapshot above.
            #ContinuousRate assign armAngleRadians :=
                armAngleRadians + derivative.armAngleRate * dt;
            #ContinuousRate assign pendulumAngleFromUprightRadians :=
                pendulumAngleFromUprightRadians + derivative.pendulumAngleRate * dt;
            #ContinuousRate assign armAngularVelocityRadiansPerSecond :=
                armAngularVelocityRadiansPerSecond + derivative.armAngularAcceleration * dt;
            #ContinuousRate assign pendulumAngularVelocityRadiansPerSecond :=
                pendulumAngularVelocityRadiansPerSecond +
                derivative.pendulumAngularAcceleration * dt;
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

        port plantPort : PendulumPhysicalStatePort;
        port upstreamPort : ~PendulumSensorPort;

        action step {
            in dt : Real;

            // Backward-Euler realization of H(s) = w*s/(s+w).
            assign estimatedArmAngularVelocityRadiansPerSecond :=
                (estimatedArmAngularVelocityRadiansPerSecond +
                 velocityFilterCutoffRadiansPerSecond *
                 (plantPort.state.armAngleRadians - previousArmAngleRadians)) /
                (1.0 + velocityFilterCutoffRadiansPerSecond * dt);
            assign estimatedPendulumAngularVelocityRadiansPerSecond :=
                (estimatedPendulumAngularVelocityRadiansPerSecond +
                 velocityFilterCutoffRadiansPerSecond *
                 (plantPort.state.pendulumAngleFromUprightRadians -
                  previousPendulumAngleFromUprightRadians)) /
                (1.0 + velocityFilterCutoffRadiansPerSecond * dt);

            assign sampledArmAngleRadians := plantPort.state.armAngleRadians;
            assign sampledPendulumAngleFromUprightRadians :=
                plantPort.state.pendulumAngleFromUprightRadians;
            assign previousArmAngleRadians := plantPort.state.armAngleRadians;
            assign previousPendulumAngleFromUprightRadians :=
                plantPort.state.pendulumAngleFromUprightRadians;
        }

        bind upstreamPort.reading.armAngleRadians = sampledArmAngleRadians;
        bind upstreamPort.reading.pendulumAngleFromUprightRadians =
            sampledPendulumAngleFromUprightRadians;
        bind upstreamPort.reading.estimatedArmAngularVelocityRadiansPerSecond =
            estimatedArmAngularVelocityRadiansPerSecond;
        bind upstreamPort.reading.estimatedPendulumAngularVelocityRadiansPerSecond =
            estimatedPendulumAngularVelocityRadiansPerSecond;
    }

    part def MotorAmplifier {
        attribute enabled : Boolean;
        attribute faulted : Boolean;
        attribute maximumVoltageMagnitude : Real;
        attribute proposedVoltage : Real;
        attribute executedVoltage : Real;

        port proposalPort : MotorVoltageCommandPort;
        port drivePort : ~MotorVoltageCommandPort;
        port statusPort : ~AmplifierStatusPort;

        action step {
            in dt : Real;

            item proposal : MotorVoltageCommand;
            accept proposal : MotorVoltageCommand via proposalPort.command;
            assign proposedVoltage := proposal.volts;

            // This is the execution relation. A fault or disabled amplifier
            // executes zero; otherwise the proposal is projected to the
            // documented voltage interval.
            if faulted or not enabled {
                assign executedVoltage := 0.0;
            }
            if not faulted and enabled and proposal.volts > maximumVoltageMagnitude {
                assign executedVoltage := maximumVoltageMagnitude;
            }
            if not faulted and enabled and proposal.volts < 0.0 - maximumVoltageMagnitude {
                assign executedVoltage := 0.0 - maximumVoltageMagnitude;
            }
            if not faulted and enabled and
               proposal.volts <= maximumVoltageMagnitude and
               proposal.volts >= 0.0 - maximumVoltageMagnitude {
                assign executedVoltage := proposal.volts;
            }
        }

        bind drivePort.command.volts = executedVoltage;
        bind statusPort.status.enabled = enabled;
        bind statusPort.status.faulted = faulted;
        bind statusPort.status.proposedVoltage = proposedVoltage;
        bind statusPort.status.executedVoltage = executedVoltage;
    }

    part def BalanceController {
        attribute targetArmAngleRadians : Real;
        attribute maximumVoltageMagnitude : Real;
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
        port amplifierStatusPort : AmplifierStatusPort;
        port proposalPort : ~MotorVoltageCommandPort;

        #Neural action def Policy {
            in armAngleRadians : Real;
            in pendulumAngleFromUprightRadians : Real;
            in estimatedArmAngularVelocityRadiansPerSecond : Real;
            in estimatedPendulumAngularVelocityRadiansPerSecond : Real;
            in targetArmAngleRadians : Real;
            in amplifierEnabled : Boolean;
            in amplifierFaulted : Boolean;
            #Completion in done : Boolean;

            out proposedMotorVoltage : Real;
        }

        #NeuralRequirement requirement def 'Neural Balance Controller Soundness' {
            subject p : Policy;

            // The equality is the experimentally exercised LQR law. The
            // amplifier independently owns the safety projection to its
            // admissible voltage interval.
            require constraint {
                ((p.amplifierFaulted or not p.amplifierEnabled)
                    implies p.proposedMotorVoltage == 0.0) and
                ((not p.amplifierFaulted and p.amplifierEnabled)
                    implies p.proposedMotorVoltage ==
                        0.0 -
                        (armAngleGain *
                            (p.armAngleRadians - p.targetArmAngleRadians) +
                         pendulumAngleGain *
                            p.pendulumAngleFromUprightRadians +
                         armAngularVelocityGain *
                            p.estimatedArmAngularVelocityRadiansPerSecond +
                         pendulumAngularVelocityGain *
                            p.estimatedPendulumAngularVelocityRadiansPerSecond))
            }
        }

        action step {
            in dt : Real;

            item reading : PendulumReading;
            accept reading : PendulumReading via sensorPort.reading;

            item amplifier : AmplifierStatus;
            accept amplifier : AmplifierStatus via amplifierStatusPort.status;

            action policyCall : Policy {
                in armAngleRadians := reading.armAngleRadians;
                in pendulumAngleFromUprightRadians :=
                    reading.pendulumAngleFromUprightRadians;
                in estimatedArmAngularVelocityRadiansPerSecond :=
                    reading.estimatedArmAngularVelocityRadiansPerSecond;
                in estimatedPendulumAngularVelocityRadiansPerSecond :=
                    reading.estimatedPendulumAngularVelocityRadiansPerSecond;
                in targetArmAngleRadians := targetArmAngleRadians;
                in amplifierEnabled := amplifier.enabled;
                in amplifierFaulted := amplifier.faulted;
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
        flow from encoder.upstreamPort to controller.sensorPort;
        connect controller.proposalPort to amplifier.proposalPort;
        flow from amplifier.drivePort to plant.motorVoltagePort;
        flow from amplifier.statusPort to controller.amplifierStatusPort;

        attribute currentTimeSeconds : Real = 0.0;

        action step {
            in dt : Real;
            #ContinuousRate assign currentTimeSeconds := currentTimeSeconds + dt;
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
        requirement def 'Fault Removes Motor Drive' {
            doc /* A faulted or disabled amplifier shall execute zero motor voltage. */
            subject s : RotaryInvertedPendulumSystem;
            require constraint {
                (s.amplifier.faulted or not s.amplifier.enabled)
                    implies s.amplifier.executedVoltage == 0.0
            }
        }

        #Prohibition
        requirement def 'Remain Inside Certified Balance Region' {
            doc /* This balance-phase model is valid only while the physical pendulum remains within the configured upright capture envelope. */
            subject s : RotaryInvertedPendulumSystem;
            require constraint {
                s.plant.pendulumAngleFromUprightRadians >=
                    0.0 - s.controller.captureAngleRadians and
                s.plant.pendulumAngleFromUprightRadians <=
                    s.controller.captureAngleRadians
            }
        }

        #Obligation
        requirement def 'Healthy Controller Supplies Feedback' {
            doc /* While the amplifier is healthy and enabled, the controller shall issue the specified state-feedback command. */
            subject s : RotaryInvertedPendulumSystem;
            require constraint {
                (s.currentTimeSeconds > 0.0 and
                 s.amplifier.enabled and not s.amplifier.faulted)
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
            #ScenarioInput attribute :>> armAngleRadians = 0.0;
            #ScenarioInput attribute :>> pendulumAngleFromUprightRadians = 0.05;
            #ScenarioInput attribute :>> armAngularVelocityRadiansPerSecond = 0.0;
            #ScenarioInput attribute :>> pendulumAngularVelocityRadiansPerSecond = 0.0;

            attribute :>> armAccelerationFromPendulum = -41.6;
            attribute :>> armAccelerationFromArmRate = -4.16;
            attribute :>> armAccelerationFromPendulumRate = 1.37;
            attribute :>> armAccelerationFromVoltage = 13.9;
            attribute :>> pendulumAccelerationFromPendulum = 72.4;
            attribute :>> pendulumAccelerationFromArmRate = -4.11;
            attribute :>> pendulumAccelerationFromPendulumRate = -2.40;
            attribute :>> pendulumAccelerationFromVoltage = 13.7;
        }

        part :>> encoder {
            attribute :>> sampledArmAngleRadians = 0.0;
            attribute :>> sampledPendulumAngleFromUprightRadians = 0.05;
            attribute :>> previousArmAngleRadians = 0.0;
            attribute :>> previousPendulumAngleFromUprightRadians = 0.05;
            attribute :>> estimatedArmAngularVelocityRadiansPerSecond = 0.0;
            attribute :>> estimatedPendulumAngularVelocityRadiansPerSecond = 0.0;
            attribute :>> velocityFilterCutoffRadiansPerSecond = 50.0;
        }

        part :>> amplifier {
            attribute :>> enabled = true;
            attribute :>> faulted = false;
            attribute :>> maximumVoltageMagnitude = 15.0;
            attribute :>> proposedVoltage = 0.0;
            attribute :>> executedVoltage = 0.0;
        }

        part :>> controller {
            #ScenarioInput attribute :>> targetArmAngleRadians = 0.0;
            attribute :>> maximumVoltageMagnitude = 15.0;
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
            plant.pendulumAngleFromUprightRadians >=
                0.0 - controller.captureAngleRadians and
            plant.pendulumAngleFromUprightRadians <=
                controller.captureAngleRadians and
            controller.targetArmAngleRadians >= -1.570796326795 and
            controller.targetArmAngleRadians <= 1.570796326795 and
            amplifier.maximumVoltageMagnitude == controller.maximumVoltageMagnitude
        }
    }
}
