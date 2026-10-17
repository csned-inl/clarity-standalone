package GEMPMSMSpeedControl {
    private import ScalarValues::*;
    private import TrigFunctions::*;
    private import RealFunctions::sqrt;
    private import RealFunctions::floor;
    private import Metaobjects::Metaobject;

    metadata def Neural :> Metaobject;
    metadata def NeuralRequirement :> Metaobject;
    metadata def Prohibition :> Metaobject;
    metadata def Obligation :> Metaobject;
    metadata def ScenarioInput :> Metaobject;
    metadata def ScenarioConstraint :> Metaobject;
    metadata def TrainingObjective :> Metaobject;
    metadata def RuntimeBinding :> Metaobject;
    metadata def Completion :> Metaobject;

    /* Source-checked benchmark model, 2026-10-14.
     * Authority: upb-lea/gym-electric-motor commit
     * b474daf9cf1ef55e9161009cb06bb996072d0df0, Cont-SC-PMSM-v0 defaults.
     * SOURCE_TRACEABILITY.csv identifies every calculation and runtime service.
     * SI scalar magnitudes are used internally; NormalizedObservation is dimensionless.
     * ODE state order: mechanical speed, d current, q current, unwrapped electrical angle.
     * SampledTransition models one 1 millisecond abc-control interval (experimental sampling variant).
     * The dq voltage is transformed at its START and held during integration.
     * Phase-current observations also use that START angle (source behavior).
     * Only the observed angle is wrapped; the ODE angle is never reset/wrapped.
     * Numerical integration and seeded randomness are source-bound runtime services;
     * gem_pmsm_runtime.py implements those services and evaluates these calculations.
     * This is not a claim of execution by CLARITY's existing scalar simulator.
     * Constraint violation is reported. The plant remains evolvable after violation.
     * Training/environment code decides whether to terminate an episode.
     * No hard tracking band/deadline or speed prohibition is added to the benchmark.
     */

    item def PhysicalState {
        attribute mechanicalSpeedRadiansPerSecond : Real;
        attribute dCurrentAmperes : Real;
        attribute qCurrentAmperes : Real;
        attribute electricalAngleRadians : Real;
    }

    item def PhysicalRates {
        attribute mechanicalAccelerationRadiansPerSecondSquared : Real;
        attribute dCurrentRateAmperesPerSecond : Real;
        attribute qCurrentRateAmperesPerSecond : Real;
        attribute electricalAngleRateRadiansPerSecond : Real;
    }

    item def ThreePhaseAction {
        attribute phaseA : Real;
        attribute phaseB : Real;
        attribute phaseC : Real;
    }

    item def BridgeVoltages {
        // Potentials relative to the centered DC bus, not phase-to-neutral.
        attribute aVolts : Real;
        attribute bVolts : Real;
        attribute cVolts : Real;
    }

    item def RotorFrameVoltages {
        attribute dVolts : Real;
        attribute qVolts : Real;
    }

    item def PhaseCurrents {
        attribute aAmperes : Real;
        attribute bAmperes : Real;
        attribute cAmperes : Real;
    }

    item def Observation {
        // Physical-unit representation. The GEM policy-facing observation
        // uses normalized versions of these same fourteen quantities.
        attribute mechanicalSpeedRadiansPerSecond : Real;
        attribute torqueNewtonMeters : Real;
        attribute aCurrentAmperes : Real;
        attribute bCurrentAmperes : Real;
        attribute cCurrentAmperes : Real;
        attribute dCurrentAmperes : Real;
        attribute qCurrentAmperes : Real;
        attribute aBridgeVolts : Real;
        attribute bBridgeVolts : Real;
        attribute cBridgeVolts : Real;
        attribute dVolts : Real;
        attribute qVolts : Real;
        attribute electricalAngleRadians : Real;
        attribute dcBusVolts : Real;
    }


    part def MotorParameters {
        // MOTOR defaults, in SI units. These are benchmark parameters.
        attribute statorResistanceOhms : Real = 0.018;
        attribute dInductanceHenries : Real = 0.00037;
        attribute qInductanceHenries : Real = 0.0012;
        attribute permanentMagnetFluxWebers : Real = 0.066;
        attribute polePairs : Integer = 3;
        attribute rotorInertiaKilogramMetersSquared : Real = 0.03883;
        attribute nominalCurrentAmperes : Real = 240.0;
        attribute currentRadiusLimitAmperes : Real = 400.0;
        attribute voltageNormalizationVolts : Real = 300.0 / 2.0;
        attribute nominalSpeedRpm : Real = 3000.0;
        attribute nominalSpeedRadiansPerSecond : Real = 3000.0 * pi / 30.0;
        attribute speedNormalizationLimitRpm : Real = 4000.0;
        // Derived from 4000 * pi / 30. This is not a speed prohibition.
        attribute speedScaleRadiansPerSecond : Real = 4000.0 * pi / 30.0;
    }

    part def LoadParameters {
        // ENV overrides a,b,c; LOAD supplies j_load and tau_decay defaults.
        attribute constantTorqueNewtonMeters : Real = 0.01;
        attribute viscousTorquePerSpeed : Real = 0.01;
        attribute quadraticTorquePerSpeedSquared : Real = 0.0;
        attribute loadInertiaKilogramMetersSquared : Real = 0.00001;
        attribute smoothingTimeSeconds : Real = 0.001;
    }

    calc def ElectromagneticTorque {
        in motorState : PhysicalState;
        in parameters : MotorParameters;
        return torqueNewtonMeters : Real =
            1.5 * parameters.polePairs *
            (parameters.permanentMagnetFluxWebers +
             (parameters.dInductanceHenries - parameters.qInductanceHenries) *
             motorState.dCurrentAmperes) * motorState.qCurrentAmperes;
    }

    calc def MechanicalLoadTorque {
        in speedRadiansPerSecond : Real;
        in parameters : LoadParameters;
        in totalInertiaKilogramMetersSquared : Real;
        attribute transitionSpeed : Real = parameters.constantTorqueNewtonMeters *
            parameters.smoothingTimeSeconds / totalInertiaKilogramMetersSquared;
        attribute linearFactor : Real = totalInertiaKilogramMetersSquared /
            parameters.smoothingTimeSeconds;
        // Algebraic transcription of LOAD._static_load, including its
        // zero-speed smoothing; zero friction has not been substituted.
        attribute constantTerm : Real =
            if speedRadiansPerSecond > transitionSpeed ?
                parameters.constantTorqueNewtonMeters else
            if speedRadiansPerSecond < 0.0 - transitionSpeed ?
                0.0 - parameters.constantTorqueNewtonMeters else
                linearFactor * speedRadiansPerSecond;
        attribute quadraticTerm : Real =
            if speedRadiansPerSecond > 0.0 ?
                parameters.quadraticTorquePerSpeedSquared *
                speedRadiansPerSecond * speedRadiansPerSecond else
            if speedRadiansPerSecond < 0.0 ?
                0.0 - parameters.quadraticTorquePerSpeedSquared *
                speedRadiansPerSecond * speedRadiansPerSecond else 0.0;
        return torqueNewtonMeters : Real = constantTerm + quadraticTerm +
            parameters.viscousTorquePerSpeed * speedRadiansPerSecond;
    }

    calc def MotorVectorField {
        in vectorState : PhysicalState;
        in voltage : RotorFrameVoltages;
        in motorParameters : MotorParameters;
        in mechanicalParameters : LoadParameters;
        attribute totalInertia : Real =
            motorParameters.rotorInertiaKilogramMetersSquared +
            mechanicalParameters.loadInertiaKilogramMetersSquared;
        calc torque : ElectromagneticTorque {
            in motorState = vectorState;
            in parameters = motorParameters;
        }
        calc resistingTorque : MechanicalLoadTorque {
            in speedRadiansPerSecond = vectorState.mechanicalSpeedRadiansPerSecond;
            in parameters = mechanicalParameters;
            in totalInertiaKilogramMetersSquared = totalInertia;
        }
        return rates : PhysicalRates {
            attribute :>> dCurrentRateAmperesPerSecond =
                (voltage.dVolts - motorParameters.statorResistanceOhms *
                 vectorState.dCurrentAmperes + motorParameters.polePairs *
                 vectorState.mechanicalSpeedRadiansPerSecond *
                 motorParameters.qInductanceHenries * vectorState.qCurrentAmperes) /
                motorParameters.dInductanceHenries;
            attribute :>> qCurrentRateAmperesPerSecond =
                (voltage.qVolts - motorParameters.statorResistanceOhms *
                 vectorState.qCurrentAmperes - motorParameters.polePairs *
                 vectorState.mechanicalSpeedRadiansPerSecond *
                 (motorParameters.dInductanceHenries * vectorState.dCurrentAmperes +
                  motorParameters.permanentMagnetFluxWebers)) /
                motorParameters.qInductanceHenries;
            attribute :>> electricalAngleRateRadiansPerSecond =
                motorParameters.polePairs * vectorState.mechanicalSpeedRadiansPerSecond;
            attribute :>> mechanicalAccelerationRadiansPerSecondSquared =
                (torque.torqueNewtonMeters - resistingTorque.torqueNewtonMeters) /
                totalInertia;
        }
    }

    calc def ContinuousBridgeExecution {
        in proposal : ThreePhaseAction;
        in supplyVoltageVolts : Real;
        // DRIVE clamps each half-bridge duty into [0,1]. The equivalent
        // signed-action clipping is written explicitly here.
        attribute executedA : Real = if proposal.phaseA > 1.0 ? 1.0 else
            if proposal.phaseA < -1.0 ? -1.0 else proposal.phaseA;
        attribute executedB : Real = if proposal.phaseB > 1.0 ? 1.0 else
            if proposal.phaseB < -1.0 ? -1.0 else proposal.phaseB;
        attribute executedC : Real = if proposal.phaseC > 1.0 ? 1.0 else
            if proposal.phaseC < -1.0 ? -1.0 else proposal.phaseC;
        return potentials : BridgeVoltages {
            attribute :>> aVolts = 0.5 * supplyVoltageVolts * executedA;
            attribute :>> bVolts = 0.5 * supplyVoltageVolts * executedB;
            attribute :>> cVolts = 0.5 * supplyVoltageVolts * executedC;
        }
    }

    calc def ClarkeParkVoltageTransform {
        in potentials : BridgeVoltages;
        in frameAngleRadians : Real;
        // FRAME.t_23 followed by FRAME.q_inv. 1/sqrt(3) is derived.
        attribute alpha : Real =
            (2.0 * potentials.aVolts - potentials.bVolts - potentials.cVolts) / 3.0;
        attribute beta : Real =
            (potentials.bVolts - potentials.cVolts) / (2.0 * cos(pi / 6.0));
        return voltage : RotorFrameVoltages {
            attribute :>> dVolts = cos(frameAngleRadians) * alpha +
                sin(frameAngleRadians) * beta;
            attribute :>> qVolts = 0.0 - sin(frameAngleRadians) * alpha +
                cos(frameAngleRadians) * beta;
        }
    }

    calc def PhaseCurrentTransform {
        in dCurrentAmperes : Real;
        in qCurrentAmperes : Real;
        in electricalAngleRadians : Real;
        attribute alpha : Real = cos(electricalAngleRadians) * dCurrentAmperes -
            sin(electricalAngleRadians) * qCurrentAmperes;
        attribute beta : Real = sin(electricalAngleRadians) * dCurrentAmperes +
            cos(electricalAngleRadians) * qCurrentAmperes;
        return currents : PhaseCurrents {
            attribute :>> aAmperes = alpha;
            attribute :>> bAmperes = -0.5 * alpha + cos(pi / 6.0) * beta;
            attribute :>> cAmperes = -0.5 * alpha - cos(pi / 6.0) * beta;
        }
    }



    part def MotorController {
        #Neural action def Policy {
            in reading : NormalizedObservation;
            in normalizedReference : Real;
            in #Completion done : Boolean;
            out phaseA : Real;
            out phaseB : Real;
            out phaseC : Real;
        }
        #NeuralRequirement requirement def 'Three Bounded Drive Proposals' {
            doc /* The policy shall propose three normalized drive commands. This is an interface-domain contract, not a speed-tracking guarantee. */
            subject policy : Policy;
            require constraint {
                policy.phaseA >= -1.0 and policy.phaseA <= 1.0 and
                policy.phaseB >= -1.0 and policy.phaseB <= 1.0 and
                policy.phaseC >= -1.0 and policy.phaseC <= 1.0
            }
        }
    }



    part def ReferenceParameters {
        attribute minimumNormalizedReference : Real = -(3000.0 * pi / 30.0) / (4000.0 * pi / 30.0);
        attribute maximumNormalizedReference : Real = (3000.0 * pi / 30.0) / (4000.0 * pi / 30.0);
        attribute minimumSigma : Real = 0.001;
        attribute maximumSigma : Real = 0.1;
        attribute minimumSubepisodeSteps : Integer = 500;
        attribute maximumSubepisodeSteps : Integer = 2000;
    }

    #TrainingObjective calc def SpeedReward {
        in physicalSpeedRadiansPerSecond : Real;
        in referenceSpeedRadiansPerSecond : Real;
        in currentRadiusExceeded : Boolean;
        attribute speedScale : Real = 4000.0 * pi / 30.0;
        attribute normalizedError : Real =
            (physicalSpeedRadiansPerSecond - referenceSpeedRadiansPerSecond) /
            speedScale;
        attribute absoluteError : Real = if normalizedError < 0.0 ?
            0.0 - normalizedError else normalizedError;
        // REWARD defaults: weight 1, error power 1, bias 0, gamma 0.9.
        // The source uses the motorState-space length 2 for bidirectional speed.
        return reward : Real = if currentRadiusExceeded ?
            -1.0 / (1.0 - 0.9) else 0.0 - absoluteError / 2.0;
    }

    item def NormalizedObservation {
        attribute omega : Real;
        attribute torque : Real;
        attribute i_a : Real;
        attribute i_b : Real;
        attribute i_c : Real;
        attribute i_sd : Real;
        attribute i_sq : Real;
        attribute u_a : Real;
        attribute u_b : Real;
        attribute u_c : Real;
        attribute u_sd : Real;
        attribute u_sq : Real;
        attribute epsilon : Real;
        attribute u_sup : Real;
    }

    calc def WrapObservedAngle {
        in rawAngle : Real;
        attribute positiveAngle : Real = rawAngle - floor(rawAngle / (2.0 * pi)) * (2.0 * pi);
        return wrapped : Real = if positiveAngle > pi ? positiveAngle - 2.0 * pi else positiveAngle;
    }

    calc def TorqueNormalization {
        in parameters : MotorParameters;
        attribute pTerm : Real = parameters.permanentMagnetFluxWebers /
            (2.0 * (parameters.dInductanceHenries - parameters.qInductanceHenries));
        attribute optimumD : Real = -pTerm / 2.0 - sqrt((pTerm / 2.0) ** 2.0 +
            parameters.nominalCurrentAmperes ** 2.0 / 2.0);
        attribute optimumQ : Real = sqrt(parameters.nominalCurrentAmperes ** 2.0 - optimumD ** 2.0);
        return torqueScale : Real = 1.5 * parameters.polePairs *
            (parameters.permanentMagnetFluxWebers +
             (parameters.dInductanceHenries - parameters.qInductanceHenries) * optimumD) * optimumQ;
    }

    calc def AssembleObservation {
        in finalState : PhysicalState;
        in startingAngle : Real;
        in bridge : BridgeVoltages;
        in heldVoltage : RotorFrameVoltages;
        in observationMotorParameters : MotorParameters;
        in supplyVolts : Real;
        calc torque : ElectromagneticTorque { in motorState = finalState; in parameters = observationMotorParameters; }
        calc currents : PhaseCurrentTransform {
            in dCurrentAmperes = finalState.dCurrentAmperes;
            in qCurrentAmperes = finalState.qCurrentAmperes;
            in electricalAngleRadians = startingAngle;
        }
        calc angle : WrapObservedAngle { in rawAngle = finalState.electricalAngleRadians; }
        return reading : Observation {
            attribute :>> mechanicalSpeedRadiansPerSecond = finalState.mechanicalSpeedRadiansPerSecond;
            attribute :>> torqueNewtonMeters = torque.torqueNewtonMeters;
            attribute :>> aCurrentAmperes = currents.currents.aAmperes;
            attribute :>> bCurrentAmperes = currents.currents.bAmperes;
            attribute :>> cCurrentAmperes = currents.currents.cAmperes;
            attribute :>> dCurrentAmperes = finalState.dCurrentAmperes;
            attribute :>> qCurrentAmperes = finalState.qCurrentAmperes;
            attribute :>> aBridgeVolts = bridge.aVolts;
            attribute :>> bBridgeVolts = bridge.bVolts;
            attribute :>> cBridgeVolts = bridge.cVolts;
            attribute :>> dVolts = heldVoltage.dVolts;
            attribute :>> qVolts = heldVoltage.qVolts;
            attribute :>> electricalAngleRadians = angle.wrapped;
            attribute :>> dcBusVolts = supplyVolts;
        }
    }

    calc def NormalizeObservation {
        in physical : Observation;
        in observationMotorParameters : MotorParameters;
        in supplyVolts : Real;
        calc torqueScaleCalculation : TorqueNormalization { in parameters = observationMotorParameters; }
        return reading : NormalizedObservation {
            attribute :>> omega = physical.mechanicalSpeedRadiansPerSecond / observationMotorParameters.speedScaleRadiansPerSecond;
            attribute :>> torque = physical.torqueNewtonMeters / torqueScaleCalculation.torqueScale;
            attribute :>> i_a = physical.aCurrentAmperes / observationMotorParameters.currentRadiusLimitAmperes;
            attribute :>> i_b = physical.bCurrentAmperes / observationMotorParameters.currentRadiusLimitAmperes;
            attribute :>> i_c = physical.cCurrentAmperes / observationMotorParameters.currentRadiusLimitAmperes;
            attribute :>> i_sd = physical.dCurrentAmperes / observationMotorParameters.currentRadiusLimitAmperes;
            attribute :>> i_sq = physical.qCurrentAmperes / observationMotorParameters.currentRadiusLimitAmperes;
            attribute :>> u_a = physical.aBridgeVolts / observationMotorParameters.voltageNormalizationVolts;
            attribute :>> u_b = physical.bBridgeVolts / observationMotorParameters.voltageNormalizationVolts;
            attribute :>> u_c = physical.cBridgeVolts / observationMotorParameters.voltageNormalizationVolts;
            attribute :>> u_sd = physical.dVolts / observationMotorParameters.voltageNormalizationVolts;
            attribute :>> u_sq = physical.qVolts / observationMotorParameters.voltageNormalizationVolts;
            attribute :>> epsilon = physical.electricalAngleRadians / pi;
            attribute :>> u_sup = physical.dcBusVolts / supplyVolts;
        }
    }

    calc def CurrentRadiusExceeded {
        in dCurrentAmperes : Real;
        in qCurrentAmperes : Real;
        in currentScaleAmperes : Real;
        return exceeded : Boolean = (dCurrentAmperes / currentScaleAmperes) ** 2.0 +
            (qCurrentAmperes / currentScaleAmperes) ** 2.0 > 1.0;
    }

    calc def ReferenceInitialValue {
        in uniformDraw : Real;
        in lowerMargin : Real;
        in upperMargin : Real;
        return referenceValue : Real = lowerMargin + (upperMargin - lowerMargin) * uniformDraw;
    }

    calc def ReferenceSubepisodeLength {
        in uniformDraw : Real;
        return count : Integer = floor(500.0 + 1500.0 * uniformDraw);
    }

    calc def ReferenceSigma {
        in uniformDraw : Real;
        // log10(0.001)=-3 and log10(0.1)=-1, exactly derived from source bounds.
        return sigma : Real = 10.0 ** (-3.0 + 2.0 * uniformDraw);
    }

    calc def ReferenceIncrement {
        in previousValue : Real;
        in gaussianIncrement : Real;
        in lowerMargin : Real;
        in upperMargin : Real;
        attribute proposed : Real = previousValue + gaussianIncrement;
        return referenceValue : Real = if proposed > upperMargin ? upperMargin else
            if proposed < lowerMargin ? lowerMargin else proposed;
    }

    #RuntimeBinding action def IntegrateDopri5 {
        doc /* Binding: gem_pmsm_runtime.ModelPlant.integrate. Stateful scipy.integrate.ode with dopri5 and default options; derivative is MotorVectorField. Reuse the integrator across control intervals, hold d/q voltage fixed; integrate to timeSeconds + intervalSeconds. No state projection or post-fault absorbing mode. */
        in initialState : PhysicalState;
        in heldVoltage : RotorFrameVoltages;
        in motorParameters : MotorParameters;
        in loadParameters : LoadParameters;
        in timeSeconds : Real;
        in intervalSeconds : Real;
        out finalState : PhysicalState;
    }

    #RuntimeBinding action def AdvanceReference {
        doc /* Binding: gem_pmsm_runtime.ModelReference. On environment reset seed NumPy SeedSequence(seed).spawn(4)[1]; RandomComponent.seed consumes spawn(1) for the initial RNG. Draw initial uniform value before next_generator consumes the next spawn(1). A subepisode draws floor(500+1500*U) steps, sigma=10**(-3+2*U), then a batch of normal(0,sigma,count) increments, clipped cumulatively. Consume the first generated reference on reset. Per step reward uses current value, then advance this service for the returned next reference. */
        in episodeSeed : Integer;
        in resetRequested : Boolean;
        out normalizedReference : Real;
    }

    action def SampledTransition {
        in incomingState : PhysicalState;
        in requestedDrive : ThreePhaseAction;
        in transitionMotorParameters : MotorParameters;
        in transitionLoadParameters : LoadParameters;
        in transitionTimeSeconds : Real;
        in referenceUsed : Real;
        attribute samplePeriodSeconds : Real = 0.001;
        attribute busVolts : Real = 420.0;
        calc commandedBridge : ContinuousBridgeExecution { in proposal = requestedDrive; in supplyVoltageVolts = busVolts; }
        calc transform : ClarkeParkVoltageTransform {
            in potentials = commandedBridge.potentials;
            in frameAngleRadians = incomingState.electricalAngleRadians;
        }
        first start;
        then action integrate : IntegrateDopri5 {
            in initialState = incomingState;
            in heldVoltage = transform.voltage;
            in motorParameters = transitionMotorParameters;
            in loadParameters = transitionLoadParameters;
            in timeSeconds = transitionTimeSeconds;
            in intervalSeconds = samplePeriodSeconds;
        }
        then done;
        calc observation : AssembleObservation {
            in finalState = integrate.finalState;
            in startingAngle = incomingState.electricalAngleRadians;
            in bridge = commandedBridge.potentials;
            in heldVoltage = transform.voltage;
            in observationMotorParameters = transitionMotorParameters;
            in supplyVolts = busVolts;
        }
        calc normalization : NormalizeObservation {
            in physical = observation.reading; in observationMotorParameters = transitionMotorParameters; in supplyVolts = busVolts;
        }
        calc violation : CurrentRadiusExceeded {
            in dCurrentAmperes = integrate.finalState.dCurrentAmperes;
            in qCurrentAmperes = integrate.finalState.qCurrentAmperes;
            in currentScaleAmperes = transitionMotorParameters.currentRadiusLimitAmperes;
        }
        calc rewardCalculation : SpeedReward {
            in physicalSpeedRadiansPerSecond = integrate.finalState.mechanicalSpeedRadiansPerSecond;
            in referenceSpeedRadiansPerSecond = referenceUsed * transitionMotorParameters.speedScaleRadiansPerSecond;
            in currentRadiusExceeded = violation.exceeded;
        }
        out finalState : PhysicalState = integrate.finalState;
        out nextObservation : NormalizedObservation = normalization.reading;
        out safetyViolation : Boolean = violation.exceeded;
        out reward : Real = rewardCalculation.reward;
    }

    calc def ResetPhysicalState {
        return initialState : PhysicalState {
            attribute :>> mechanicalSpeedRadiansPerSecond = 0.0;
            attribute :>> dCurrentAmperes = 0.0;
            attribute :>> qCurrentAmperes = 0.0;
            attribute :>> electricalAngleRadians = 0.0;
        }
    }

    calc def ResetObservation {
        in resetParameters : MotorParameters;
        calc initial : ResetPhysicalState;
        calc resetBridge : ContinuousBridgeExecution {
            in proposal : ThreePhaseAction {
                attribute :>> phaseA = -1.0;
                attribute :>> phaseB = -1.0;
                attribute :>> phaseC = -1.0;
            }
            in supplyVoltageVolts = 420.0;
        }
        calc resetVoltage : ClarkeParkVoltageTransform {
            in potentials = resetBridge.potentials;
            in frameAngleRadians = 0.0;
        }
        calc physicalReading : AssembleObservation {
            in finalState = initial.initialState;
            in startingAngle = 0.0;
            in bridge = resetBridge.potentials;
            in heldVoltage = resetVoltage.voltage;
            in observationMotorParameters = resetParameters;
            in supplyVolts = 420.0;
        }
        calc normalized : NormalizeObservation {
            in physical = physicalReading.reading;
            in observationMotorParameters = resetParameters;
            in supplyVolts = 420.0;
        }
        return reading : NormalizedObservation = normalized.reading;
    }

    part def PmsmSpeedControlSystem {
        part benchmarkMotorParameters : MotorParameters;
        part benchmarkLoadParameters : LoadParameters;
        part referenceParameters : ReferenceParameters;
        part controller : MotorController;
        item plantState : PhysicalState;
        item observation : NormalizedObservation;
        attribute currentReference : Real;
        // Project-selected trial horizon; no change to physical GEM dynamics.
        // Completion is flagged on the final decision, then its response is
        // integrated and checked before reporting terminal to the trainer.
        attribute trialDurationSeconds : Real = 3.0;
        attribute trialControlSteps : Integer = 3000;
        attribute completedControlSteps : Integer := 0;
        attribute elapsedSeconds : Real := 0.0;
        attribute lastSafetyViolation : Boolean := false;

        action reset {
            in resetSeed : Integer;
            calc initial : ResetPhysicalState;
            calc resetReading : ResetObservation { in resetParameters = benchmarkMotorParameters; }
            first start;
            then assign plantState := initial.initialState;
            then assign observation := resetReading.reading;
            then assign elapsedSeconds := 0.0;
            then assign completedControlSteps := 0;
            then assign lastSafetyViolation := false;
            then action initialReference : AdvanceReference {
                in episodeSeed = resetSeed;
                in resetRequested = true;
            }
            then assign currentReference := initialReference.normalizedReference;
            then done;
        }

        action cycle {
            in cycleSeed : Integer;
            first start;
            then action policyCall : MotorController::Policy {
                in reading = observation;
                in normalizedReference = currentReference;
                in done = completedControlSteps + 1 >= trialControlSteps;
            }
            then action advance : SampledTransition {
                in incomingState = plantState;
                in requestedDrive : ThreePhaseAction {
                    attribute :>> phaseA = policyCall.phaseA;
                    attribute :>> phaseB = policyCall.phaseB;
                    attribute :>> phaseC = policyCall.phaseC;
                }
                in transitionMotorParameters = benchmarkMotorParameters;
                in transitionLoadParameters = benchmarkLoadParameters;
                in transitionTimeSeconds = elapsedSeconds;
                in referenceUsed = currentReference;
            }
            then assign plantState := advance.finalState;
            then assign observation := advance.nextObservation;
            then assign lastSafetyViolation := advance.safetyViolation;
            then assign elapsedSeconds := elapsedSeconds + 0.001;
            then assign completedControlSteps := completedControlSteps + 1;
            then action nextReference : AdvanceReference {
                in episodeSeed = cycleSeed;
                in resetRequested = false;
            }
            then assign currentReference := nextReference.normalizedReference;
            then done;
        }

        #Prohibition requirement def 'Sampled Current Radius Not Exceeded' {
            doc /* The benchmark's sampled safety property. It is checked, never assumed to restrict reachable plant states. Equality at the boundary passes. */
            subject system : PmsmSpeedControlSystem;
            require constraint {
                not CurrentRadiusExceeded(system.plantState.dCurrentAmperes,
                    system.plantState.qCurrentAmperes,
                    system.benchmarkMotorParameters.currentRadiusLimitAmperes)
            }
        }

        #ScenarioConstraint requirement def 'Published Reference Envelope' {
            subject system : PmsmSpeedControlSystem;
            require constraint {
                system.currentReference >= system.referenceParameters.minimumNormalizedReference and
                system.currentReference <= system.referenceParameters.maximumNormalizedReference
            }
        }
    }
    part system : PmsmSpeedControlSystem;
}
