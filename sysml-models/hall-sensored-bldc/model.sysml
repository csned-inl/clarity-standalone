package HallSensoredBrushlessMotor {
    private import ScalarValues::*;

    // CLARITY annotations used by the standalone reference models.
    metadata def Neural;
    metadata def NeuralRequirement;
    metadata def Prohibition;
    metadata def Obligation;
    metadata def Termination;
    metadata def ScenarioInput;
    metadata def ScenarioConstraint;

    // This is the RUN-phase abstraction of NXP's Hall-sensored six-step
    // control example for the Sunrise 42BLY3A78-24110 motor. It deliberately
    // does not amalgamate parameters from unrelated motors. Physical state,
    // sampled state, proposed duty, and executed duty are distinct symbols.
    // Startup, calibration, alignment, thermal dynamics, and external load
    // dynamics are outside this first model's declared scope.

    item def MotorPhysicalState {
        attribute rotorMechanicalAngleRadians : Real;
        attribute rotorMechanicalSpeedRadiansPerSecond : Real;
        attribute energizedPairCurrentAmperes : Real;
        attribute electricalSector : Integer;
        attribute electricalAngleWithinSectorRadians : Real;
    }

    port def MotorPhysicalStatePort {
        in item state : MotorPhysicalState;
    }

    item def HallMotorReading {
        attribute hallA : Boolean;
        attribute hallB : Boolean;
        attribute hallC : Boolean;
        attribute hallCode : Integer;
        attribute estimatedMechanicalSpeedRadiansPerSecond : Real;
        attribute sampledPairCurrentAmperes : Real;
        attribute sampledDcBusVoltageVolts : Real;
    }

    port def HallMotorSensorPort {
        in item reading : HallMotorReading;
    }

    item def SignedDutyCommand {
        attribute fraction : Real;
    }

    port def SignedDutyCommandPort {
        in item command : SignedDutyCommand;
    }

    item def CommutatedVoltage {
        attribute signedPhasePairVoltageVolts : Real;
        attribute highSidePwmPhase : Integer;
        attribute lowSideOnPhase : Integer;
        attribute disconnectedPhase : Integer;
    }

    port def CommutatedVoltagePort {
        in item voltage : CommutatedVoltage;
    }

    item def MotorDerivative {
        attribute mechanicalAngleRate : Real;
        attribute mechanicalSpeedRate : Real;
        attribute energizedPairCurrentRate : Real;
        attribute electricalAngleRate : Real;
        attribute predictedElectricalAngleWithinSectorRadians : Real;
    }

    part def AveragedTwoPhaseMotorPlant {
        // Continuous physical state. electricalSector and the within-sector
        // angle are a quotient/remainder representation of rotor angle; they
        // are not Hall measurements.
        attribute rotorMechanicalAngleRadians : Real;
        attribute rotorMechanicalSpeedRadiansPerSecond : Real;
        attribute energizedPairCurrentAmperes : Real;
        attribute electricalSector : Integer;
        attribute electricalAngleWithinSectorRadians : Real;

        // Exact Sunrise motor data from NXP's named parameter file.
        attribute phaseResistanceOhms : Real;
        attribute dAxisInductanceHenries : Real;
        attribute qAxisInductanceHenries : Real;
        attribute backEmfConstantVoltSecondsPerRadian : Real;
        attribute torqueConstantNewtonMetersPerAmpere : Real;
        attribute rotorInertiaKilogramMetersSquared : Real;
        attribute polePairs : Integer;

        // The two-phase averaged relation follows NXP AN12435's declared
        // six-step abstraction: two phases conduct and one is disconnected.
        // q-axis inductance is used for this torque-channel abstraction; no
        // unreported phase inductance or friction coefficient is invented.
        attribute electricalSectorWidthRadians : Real;
        attribute commutationSamplePeriodSeconds : Real;

        port drivePort : CommutatedVoltagePort;
        port physicalStatePort : ~MotorPhysicalStatePort;

        action step {
            in dt : Real;

            item derivative : MotorDerivative;
            assign derivative.mechanicalAngleRate :=
                rotorMechanicalSpeedRadiansPerSecond;
            assign derivative.mechanicalSpeedRate :=
                (torqueConstantNewtonMetersPerAmpere *
                    energizedPairCurrentAmperes) /
                rotorInertiaKilogramMetersSquared;
            assign derivative.energizedPairCurrentRate :=
                (drivePort.voltage.signedPhasePairVoltageVolts -
                 2.0 * phaseResistanceOhms * energizedPairCurrentAmperes -
                 2.0 * backEmfConstantVoltSecondsPerRadian *
                    rotorMechanicalSpeedRadiansPerSecond) /
                (2.0 * qAxisInductanceHenries);
            assign derivative.electricalAngleRate :=
                polePairs * rotorMechanicalSpeedRadiansPerSecond;
            assign derivative.predictedElectricalAngleWithinSectorRadians :=
                electricalAngleWithinSectorRadians +
                derivative.electricalAngleRate *
                    commutationSamplePeriodSeconds;

            // Project-defined forward-Euler realization at the documented
            // 50 microsecond current-sampling period. All derivatives above
            // are taken from the same pre-update physical snapshot.
            #ContinuousRate assign rotorMechanicalAngleRadians :=
                rotorMechanicalAngleRadians +
                derivative.mechanicalAngleRate *
                    commutationSamplePeriodSeconds;
            #ContinuousRate assign rotorMechanicalSpeedRadiansPerSecond :=
                rotorMechanicalSpeedRadiansPerSecond +
                derivative.mechanicalSpeedRate *
                    commutationSamplePeriodSeconds;
            #ContinuousRate assign energizedPairCurrentAmperes :=
                energizedPairCurrentAmperes +
                derivative.energizedPairCurrentRate *
                    commutationSamplePeriodSeconds;

            // At the declared nameplate speed, one 50 microsecond step is
            // much smaller than one 60 electrical-degree Hall sector. These
            // branches therefore perform at most one exact sector crossing.
            if derivative.predictedElectricalAngleWithinSectorRadians >=
                    electricalSectorWidthRadians {
                assign electricalAngleWithinSectorRadians :=
                    derivative.predictedElectricalAngleWithinSectorRadians -
                    electricalSectorWidthRadians;
                if electricalSector == 5 {
                    assign electricalSector := 0;
                } else {
                    assign electricalSector := electricalSector + 1;
                }
            }
            if derivative.predictedElectricalAngleWithinSectorRadians < 0.0 {
                assign electricalAngleWithinSectorRadians :=
                    derivative.predictedElectricalAngleWithinSectorRadians +
                    electricalSectorWidthRadians;
                if electricalSector == 0 {
                    assign electricalSector := 5;
                } else {
                    assign electricalSector := electricalSector - 1;
                }
            }
            if derivative.predictedElectricalAngleWithinSectorRadians >= 0.0 and
               derivative.predictedElectricalAngleWithinSectorRadians <
                    electricalSectorWidthRadians {
                assign electricalAngleWithinSectorRadians :=
                    derivative.predictedElectricalAngleWithinSectorRadians;
            }
        }

        bind physicalStatePort.state.rotorMechanicalAngleRadians =
            rotorMechanicalAngleRadians;
        bind physicalStatePort.state.rotorMechanicalSpeedRadiansPerSecond =
            rotorMechanicalSpeedRadiansPerSecond;
        bind physicalStatePort.state.energizedPairCurrentAmperes =
            energizedPairCurrentAmperes;
        bind physicalStatePort.state.electricalSector = electricalSector;
        bind physicalStatePort.state.electricalAngleWithinSectorRadians =
            electricalAngleWithinSectorRadians;
    }

    part def HallSensorAndSpeedEstimator {
        // These sampled quantities remain distinct from the physical plant.
        attribute sampledElectricalSector : Integer;
        attribute previousElectricalSector : Integer;
        attribute hallA : Boolean;
        attribute hallB : Boolean;
        attribute hallC : Boolean;
        attribute hallCode : Integer;
        attribute sampledPairCurrentAmperes : Real;
        attribute estimatedMechanicalSpeedRadiansPerSecond : Real;
        attribute secondsSinceLastHallEvent : Real;
        attribute dcBusVoltageVolts : Real;
        attribute polePairs : Integer;
        attribute electricalSectorWidthRadians : Real;
        attribute commutationSamplePeriodSeconds : Real;

        port plantPort : MotorPhysicalStatePort;
        port controllerPort : ~HallMotorSensorPort;
        port commutatorPort : ~HallMotorSensorPort;

        action step {
            in dt : Real;

            assign secondsSinceLastHallEvent :=
                secondsSinceLastHallEvent + commutationSamplePeriodSeconds;
            assign sampledElectricalSector :=
                plantPort.state.electricalSector;
            assign sampledPairCurrentAmperes :=
                plantPort.state.energizedPairCurrentAmperes;

            if sampledElectricalSector == previousElectricalSector + 1 or
               previousElectricalSector == 5 and sampledElectricalSector == 0 {
                assign estimatedMechanicalSpeedRadiansPerSecond :=
                    electricalSectorWidthRadians /
                    (polePairs * secondsSinceLastHallEvent);
                assign secondsSinceLastHallEvent := 0.0;
                assign previousElectricalSector := sampledElectricalSector;
            }
            if previousElectricalSector == sampledElectricalSector + 1 or
               previousElectricalSector == 0 and sampledElectricalSector == 5 {
                assign estimatedMechanicalSpeedRadiansPerSecond :=
                    0.0 - electricalSectorWidthRadians /
                    (polePairs * secondsSinceLastHallEvent);
                assign secondsSinceLastHallEvent := 0.0;
                assign previousElectricalSector := sampledElectricalSector;
            }

            // Exact Sunrise Hall sequence from NXP's S32M244 table:
            // sector index 0..5 maps to 110, 100, 101, 001, 011, 010.
            if sampledElectricalSector == 0 {
                assign hallA := true;
                assign hallB := true;
                assign hallC := false;
                assign hallCode := 6;
            }
            if sampledElectricalSector == 1 {
                assign hallA := true;
                assign hallB := false;
                assign hallC := false;
                assign hallCode := 4;
            }
            if sampledElectricalSector == 2 {
                assign hallA := true;
                assign hallB := false;
                assign hallC := true;
                assign hallCode := 5;
            }
            if sampledElectricalSector == 3 {
                assign hallA := false;
                assign hallB := false;
                assign hallC := true;
                assign hallCode := 1;
            }
            if sampledElectricalSector == 4 {
                assign hallA := false;
                assign hallB := true;
                assign hallC := true;
                assign hallCode := 3;
            }
            if sampledElectricalSector == 5 {
                assign hallA := false;
                assign hallB := true;
                assign hallC := false;
                assign hallCode := 2;
            }

            item reading : HallMotorReading;
            assign reading.hallA := hallA;
            assign reading.hallB := hallB;
            assign reading.hallC := hallC;
            assign reading.hallCode := hallCode;
            assign reading.estimatedMechanicalSpeedRadiansPerSecond :=
                estimatedMechanicalSpeedRadiansPerSecond;
            assign reading.sampledPairCurrentAmperes :=
                sampledPairCurrentAmperes;
            assign reading.sampledDcBusVoltageVolts := dcBusVoltageVolts;
            send reading via controllerPort;
            send reading via commutatorPort;
        }
    }

    part def HallCommutatedDrive {
        attribute proposedSignedDutyFraction : Real;
        attribute boundedProposedSignedDutyFraction : Real;
        attribute executedSignedDutyFraction : Real;
        attribute sampledPairCurrentAmperes : Real;
        attribute sampledHallCode : Integer;
        attribute dcBusVoltageVolts : Real;
        attribute maximumDutyMagnitude : Real;
        attribute currentLimitAmperes : Real;
        attribute hallFault : Boolean;
        attribute highSidePwmPhase : Integer;
        attribute lowSideOnPhase : Integer;
        attribute disconnectedPhase : Integer;
        attribute signedPhasePairVoltageVolts : Real;

        port proposalPort : SignedDutyCommandPort;
        port hallPort : HallMotorSensorPort;
        port voltagePort : ~CommutatedVoltagePort;

        // The speed controller's proposal is held between its 1 ms updates.
        state def DutyProposalBehavior {
            entry; then waiting;
            state waiting;

            transition above_duty_limit
                first waiting
                accept proposal : SignedDutyCommand via proposalPort
                if proposal.fraction > maximumDutyMagnitude
                do action {
                    assign proposedSignedDutyFraction := proposal.fraction;
                    assign boundedProposedSignedDutyFraction :=
                        maximumDutyMagnitude;
                }
                then waiting;

            transition below_duty_limit
                first waiting
                accept proposal : SignedDutyCommand via proposalPort
                if proposal.fraction < 0.0 - maximumDutyMagnitude
                do action {
                    assign proposedSignedDutyFraction := proposal.fraction;
                    assign boundedProposedSignedDutyFraction :=
                        0.0 - maximumDutyMagnitude;
                }
                then waiting;

            transition inside_duty_limit
                first waiting
                accept proposal : SignedDutyCommand via proposalPort
                if proposal.fraction <= maximumDutyMagnitude and
                   proposal.fraction >= 0.0 - maximumDutyMagnitude
                do action {
                    assign proposedSignedDutyFraction := proposal.fraction;
                    assign boundedProposedSignedDutyFraction := proposal.fraction;
                }
                then waiting;
        }

        exhibit state dutyProposalBehavior : DutyProposalBehavior;

        action step {
            in dt : Real;

            item reading : HallMotorReading;
            accept reading : HallMotorReading via hallPort.reading;
            assign sampledPairCurrentAmperes :=
                reading.sampledPairCurrentAmperes;
            assign sampledHallCode := reading.hallCode;
            assign dcBusVoltageVolts := reading.sampledDcBusVoltageVolts;

            // 000 and 111 are invalid Hall states. The NXP reference reports
            // faults and disables PWM; this abstraction gives that externally
            // visible behavior without inventing diagnostic timing.
            if sampledHallCode < 1 or sampledHallCode > 6 {
                assign hallFault := true;
                assign executedSignedDutyFraction := 0.0;
                assign highSidePwmPhase := 0;
                assign lowSideOnPhase := 0;
                assign disconnectedPhase := 0;
            }
            if sampledHallCode >= 1 and sampledHallCode <= 6 {
                assign hallFault := false;

                // Source-faithful current-limiting direction: once measured
                // current reaches the configured limit, the drive does not
                // apply additional voltage in the same current direction.
                if sampledPairCurrentAmperes >= currentLimitAmperes and
                   boundedProposedSignedDutyFraction > 0.0 {
                    assign executedSignedDutyFraction := 0.0;
                }
                if sampledPairCurrentAmperes <= 0.0 - currentLimitAmperes and
                   boundedProposedSignedDutyFraction < 0.0 {
                    assign executedSignedDutyFraction := 0.0;
                }
                if (sampledPairCurrentAmperes < currentLimitAmperes or
                    boundedProposedSignedDutyFraction <= 0.0) and
                   (sampledPairCurrentAmperes > 0.0 - currentLimitAmperes or
                    boundedProposedSignedDutyFraction >= 0.0) {
                    assign executedSignedDutyFraction :=
                        boundedProposedSignedDutyFraction;
                }

                // NXP's double-buffered FTM update is represented atomically:
                // the applicable phase tuple changes when the Hall code does.
                // Phase identifiers are A=1, B=2, C=3, and 0=all disconnected.
                if executedSignedDutyFraction >= 0.0 and sampledHallCode == 6 {
                    assign highSidePwmPhase := 3;
                    assign lowSideOnPhase := 2;
                    assign disconnectedPhase := 1;
                }
                if executedSignedDutyFraction >= 0.0 and sampledHallCode == 4 {
                    assign highSidePwmPhase := 3;
                    assign lowSideOnPhase := 1;
                    assign disconnectedPhase := 2;
                }
                if executedSignedDutyFraction >= 0.0 and sampledHallCode == 5 {
                    assign highSidePwmPhase := 2;
                    assign lowSideOnPhase := 1;
                    assign disconnectedPhase := 3;
                }
                if executedSignedDutyFraction >= 0.0 and sampledHallCode == 1 {
                    assign highSidePwmPhase := 2;
                    assign lowSideOnPhase := 3;
                    assign disconnectedPhase := 1;
                }
                if executedSignedDutyFraction >= 0.0 and sampledHallCode == 3 {
                    assign highSidePwmPhase := 1;
                    assign lowSideOnPhase := 3;
                    assign disconnectedPhase := 2;
                }
                if executedSignedDutyFraction >= 0.0 and sampledHallCode == 2 {
                    assign highSidePwmPhase := 1;
                    assign lowSideOnPhase := 2;
                    assign disconnectedPhase := 3;
                }

                if executedSignedDutyFraction < 0.0 and sampledHallCode == 6 {
                    assign highSidePwmPhase := 2;
                    assign lowSideOnPhase := 3;
                    assign disconnectedPhase := 1;
                }
                if executedSignedDutyFraction < 0.0 and sampledHallCode == 2 {
                    assign highSidePwmPhase := 2;
                    assign lowSideOnPhase := 1;
                    assign disconnectedPhase := 3;
                }
                if executedSignedDutyFraction < 0.0 and sampledHallCode == 3 {
                    assign highSidePwmPhase := 3;
                    assign lowSideOnPhase := 1;
                    assign disconnectedPhase := 2;
                }
                if executedSignedDutyFraction < 0.0 and sampledHallCode == 1 {
                    assign highSidePwmPhase := 3;
                    assign lowSideOnPhase := 2;
                    assign disconnectedPhase := 1;
                }
                if executedSignedDutyFraction < 0.0 and sampledHallCode == 5 {
                    assign highSidePwmPhase := 1;
                    assign lowSideOnPhase := 2;
                    assign disconnectedPhase := 3;
                }
                if executedSignedDutyFraction < 0.0 and sampledHallCode == 4 {
                    assign highSidePwmPhase := 1;
                    assign lowSideOnPhase := 3;
                    assign disconnectedPhase := 2;
                }
            }

            assign signedPhasePairVoltageVolts :=
                executedSignedDutyFraction * dcBusVoltageVolts;
        }

        bind voltagePort.voltage.signedPhasePairVoltageVolts =
            signedPhasePairVoltageVolts;
        bind voltagePort.voltage.highSidePwmPhase = highSidePwmPhase;
        bind voltagePort.voltage.lowSideOnPhase = lowSideOnPhase;
        bind voltagePort.voltage.disconnectedPhase = disconnectedPhase;
    }

    part def SpeedController {
        attribute targetMechanicalSpeedRadiansPerSecond : Real;
        attribute completionSpeedToleranceRadiansPerSecond : Real;
        attribute speedControlTickCount : Integer;
        attribute speedControlTicksPerUpdate : Integer;
        attribute lastProposedSignedDutyFraction : Real;
        attribute lastObservedMechanicalSpeedRadiansPerSecond : Real;
        attribute lastObservedPairCurrentAmperes : Real;
        attribute lastObservedHallCode : Integer;

        port sensorPort : HallMotorSensorPort;
        port proposalPort : ~SignedDutyCommandPort;

        #Neural action def Policy {
            in estimatedMechanicalSpeedRadiansPerSecond : Real;
            in sampledPairCurrentAmperes : Real;
            in hallCode : Integer;
            in targetMechanicalSpeedRadiansPerSecond : Real;
            #Completion in done : Boolean;

            out proposedSignedDutyFraction : Real;
        }

        #NeuralRequirement requirement def 'Neural Speed Controller Soundness' {
            subject p : Policy;
            require constraint {
                p.proposedSignedDutyFraction >= -1.0 and
                p.proposedSignedDutyFraction <= 1.0 and
                ((p.hallCode >= 1 and p.hallCode <= 6) or
                    p.proposedSignedDutyFraction == 0.0)
            }
        }

        action step {
            in dt : Real;

            item reading : HallMotorReading;
            accept reading : HallMotorReading via sensorPort.reading;
            assign lastObservedMechanicalSpeedRadiansPerSecond :=
                reading.estimatedMechanicalSpeedRadiansPerSecond;
            assign lastObservedPairCurrentAmperes :=
                reading.sampledPairCurrentAmperes;
            assign lastObservedHallCode := reading.hallCode;

            if speedControlTickCount >= speedControlTicksPerUpdate - 1 {
                action policyCall : Policy {
                    in estimatedMechanicalSpeedRadiansPerSecond :=
                        reading.estimatedMechanicalSpeedRadiansPerSecond;
                    in sampledPairCurrentAmperes :=
                        reading.sampledPairCurrentAmperes;
                    in hallCode := reading.hallCode;
                    in targetMechanicalSpeedRadiansPerSecond :=
                        targetMechanicalSpeedRadiansPerSecond;
                    in done :=
                        reading.estimatedMechanicalSpeedRadiansPerSecond >=
                            targetMechanicalSpeedRadiansPerSecond -
                            completionSpeedToleranceRadiansPerSecond and
                        reading.estimatedMechanicalSpeedRadiansPerSecond <=
                            targetMechanicalSpeedRadiansPerSecond +
                            completionSpeedToleranceRadiansPerSecond;
                }

                assign lastProposedSignedDutyFraction :=
                    policyCall.proposedSignedDutyFraction;
                item command : SignedDutyCommand;
                assign command.fraction :=
                    policyCall.proposedSignedDutyFraction;
                send command via proposalPort;
                assign speedControlTickCount := 0;
            } else {
                assign speedControlTickCount := speedControlTickCount + 1;
            }
        }
    }

    part def HallSensoredBrushlessMotorSystem {
        part plant : AveragedTwoPhaseMotorPlant;
        part sensor : HallSensorAndSpeedEstimator;
        part drive : HallCommutatedDrive;
        part controller : SpeedController;

        flow from plant.physicalStatePort to sensor.plantPort;
        connect sensor.controllerPort to controller.sensorPort;
        connect sensor.commutatorPort to drive.hallPort;
        connect controller.proposalPort to drive.proposalPort;
        flow from drive.voltagePort to plant.drivePort;

        attribute currentTimeSeconds : Real = 0.0;
        attribute commutationSamplePeriodSeconds : Real = 0.00005;

        action step {
            in dt : Real;
            #ContinuousRate assign currentTimeSeconds :=
                currentTimeSeconds + commutationSamplePeriodSeconds;
        }

        #Prohibition
        requirement def 'Executed Duty Within Authorized Range' {
            doc /* Executed PWM duty shall remain in the normalized inverter range. */
            subject s : HallSensoredBrushlessMotorSystem;
            require constraint {
                s.drive.executedSignedDutyFraction >=
                    0.0 - s.drive.maximumDutyMagnitude and
                s.drive.executedSignedDutyFraction <=
                    s.drive.maximumDutyMagnitude
            }
        }

        #Prohibition
        requirement def 'Invalid Hall State Disables Drive' {
            doc /* Invalid 000 or 111 Hall input shall produce zero executed duty and disconnect all phases. */
            subject s : HallSensoredBrushlessMotorSystem;
            require constraint {
                (s.drive.sampledHallCode < 1 or s.drive.sampledHallCode > 6)
                    implies
                    s.drive.executedSignedDutyFraction == 0.0 and
                    s.drive.highSidePwmPhase == 0 and
                    s.drive.lowSideOnPhase == 0 and
                    s.drive.disconnectedPhase == 0
            }
        }

        #Prohibition
        requirement def 'Current Limit Opposes Further Increase' {
            doc /* At the measured current boundary, same-direction applied voltage is inhibited. */
            subject s : HallSensoredBrushlessMotorSystem;
            require constraint {
                (s.drive.sampledPairCurrentAmperes >=
                    s.drive.currentLimitAmperes
                    implies s.drive.executedSignedDutyFraction <= 0.0) and
                (s.drive.sampledPairCurrentAmperes <=
                    0.0 - s.drive.currentLimitAmperes
                    implies s.drive.executedSignedDutyFraction >= 0.0)
            }
        }

        #Obligation
        requirement def 'Controller Supplies Bounded Duty Proposal' {
            doc /* Every issued speed-controller proposal shall satisfy the normalized policy contract. */
            subject s : HallSensoredBrushlessMotorSystem;
            require constraint {
                s.currentTimeSeconds > 0.001 implies
                    s.controller.lastProposedSignedDutyFraction >= -1.0 and
                    s.controller.lastProposedSignedDutyFraction <= 1.0
            }
        }
    }

    part system : HallSensoredBrushlessMotorSystem {
        part :>> plant {
            // RUN begins after alignment, at rest in the middle of sector 0.
            attribute :>> rotorMechanicalAngleRadians = 0.0;
            attribute :>> rotorMechanicalSpeedRadiansPerSecond = 0.0;
            attribute :>> energizedPairCurrentAmperes = 0.0;
            attribute :>> electricalSector = 0;
            attribute :>> electricalAngleWithinSectorRadians = 0.523598775598;

            attribute :>> phaseResistanceOhms = 0.192;
            attribute :>> dAxisInductanceHenries = 0.000096;
            attribute :>> qAxisInductanceHenries = 0.000107;
            attribute :>> backEmfConstantVoltSecondsPerRadian = 0.005872;
            attribute :>> torqueConstantNewtonMetersPerAmpere = 0.010614;
            attribute :>> rotorInertiaKilogramMetersSquared = 0.000012;
            attribute :>> polePairs = 2;
            attribute :>> electricalSectorWidthRadians = 1.047197551197;
            attribute :>> commutationSamplePeriodSeconds = 0.00005;
        }

        part :>> sensor {
            attribute :>> sampledElectricalSector = 0;
            attribute :>> previousElectricalSector = 0;
            attribute :>> hallA = true;
            attribute :>> hallB = true;
            attribute :>> hallC = false;
            attribute :>> hallCode = 6;
            attribute :>> sampledPairCurrentAmperes = 0.0;
            attribute :>> estimatedMechanicalSpeedRadiansPerSecond = 0.0;
            attribute :>> secondsSinceLastHallEvent = 0.0;
            // NXP BLDC_KIT supplied operating point, distinct from the
            // motor's 24 V nameplate rating.
            attribute :>> dcBusVoltageVolts = 12.0;
            attribute :>> polePairs = 2;
            attribute :>> electricalSectorWidthRadians = 1.047197551197;
            attribute :>> commutationSamplePeriodSeconds = 0.00005;
        }

        part :>> drive {
            attribute :>> proposedSignedDutyFraction = 0.0;
            attribute :>> boundedProposedSignedDutyFraction = 0.0;
            attribute :>> executedSignedDutyFraction = 0.0;
            attribute :>> sampledPairCurrentAmperes = 0.0;
            attribute :>> sampledHallCode = 6;
            attribute :>> dcBusVoltageVolts = 12.0;
            attribute :>> maximumDutyMagnitude = 1.0;
            // Motor nameplate current. The model does not substitute the
            // threshold of a different board/application.
            attribute :>> currentLimitAmperes = 6.0;
            attribute :>> hallFault = false;
            attribute :>> highSidePwmPhase = 3;
            attribute :>> lowSideOnPhase = 2;
            attribute :>> disconnectedPhase = 1;
            attribute :>> signedPhasePairVoltageVolts = 0.0;
        }

        part :>> controller {
            // The target is a scenario input, not an intrinsic motor value.
            #ScenarioInput attribute :>>
                targetMechanicalSpeedRadiansPerSecond = 314.159265358979;
            attribute :>> completionSpeedToleranceRadiansPerSecond = 5.0;
            attribute :>> speedControlTickCount = 0;
            // 20 * 50 microseconds = NXP's documented 1 ms speed period.
            attribute :>> speedControlTicksPerUpdate = 20;
            attribute :>> lastProposedSignedDutyFraction = 0.0;
            attribute :>> lastObservedMechanicalSpeedRadiansPerSecond = 0.0;
            attribute :>> lastObservedPairCurrentAmperes = 0.0;
            attribute :>> lastObservedHallCode = 6;
        }

        #ScenarioConstraint constraint scenarioConstraints {
            controller.targetMechanicalSpeedRadiansPerSecond >=
                -942.477796076938 and
            controller.targetMechanicalSpeedRadiansPerSecond <=
                942.477796076938 and
            plant.commutationSamplePeriodSeconds ==
                commutationSamplePeriodSeconds and
            sensor.commutationSamplePeriodSeconds ==
                commutationSamplePeriodSeconds and
            sensor.dcBusVoltageVolts == drive.dcBusVoltageVolts
        }
    }
}
