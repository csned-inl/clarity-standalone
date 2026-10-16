# Additional source material for the Sunrise Hall motor

Research recorded 2026-10-16. Motor: **Sunrise 42BLY3A78-24110**.
This register records evidence and its limits; it does not certify the SysML
implementation or change its equations, controller, shield, or pipeline.

## Findings from the expanded search

| Question | Evidence | Conclusion |
|---|---|---|
| Does NXP publish applicable physical equations? | AN13767 section 3.2, printed pages 4–5 [S1], gives three-phase winding voltage/flux equations and their dq representation. Its phase PM flux uses cosines separated by 120 electrical degrees. AN13902 [S2] identifies the exact Sunrise motor and refers to AN13767 for these equations. | A source-backed fundamental PMSM mathematical model exists. The assembly of a conventional plant is not an unspecified mystery. |
| Is there a published simulation for the kit motor? | MathWorks' MCSPTE1AK344 example [S5–S8] includes runnable simulation models. Both motor models instantiate the Interior PMSM block, using the supplied motor parameters. | A vendor-authored simulation precedent exists for this kit. |
| Is the actual motor back-EMF exactly sinusoidal? | NXP publishes a fundamental-harmonic model [S1]. MathWorks explicitly uses a sinusoidal-back-EMF plant [S8–S9]. | These support a sinusoidal modeling approximation. No exact-part measured waveform, harmonic spectrum, or approximation-error bound was found in the inspected sources. |
| Is friction specified? | MathWorks' open- and closed-loop initialization scripts [S6–S7] set B = 0.1e-6 kg m²/s. The plant mechanical parameter is [J, B, 0], with the final entry representing static-friction torque [S8–S9]. | A published example uses viscous damping of 1e-7 N m s/rad and zero static friction. No measurement or identification provenance for those settings was found. They must not be described as measured NXP specifications. |
| What is the inertia? | NXP's exact-part profiles [S3–S4, S10–S11] and its Hall/FOC MBDT source archive [S12] list J = 0.12e-4 = 1.2e-5 kg m². MathWorks repeats this value [S6–S7]. | The numerical inertia value is published, not invented by this project. |
| Does that inertia include the attached disc? | NXP source headers call it drive inertia; the MCAT UI calls it motor inertia. NXP's kit includes a rotor disc [S13]. MathWorks' block defines J as combined motor/load inertia [S9], but the example gives no disc measurement or explicit inclusion statement. | Disc inclusion remains unresolved. The block's generic definition does not establish what was measured for the example value. |

## Source register

### NXP physical model and exact-part parameter sources

**S1 — AN13767, 3-phase Sensorless PMSM Motor Control Kit with S32K344
using RTD Low Level API**, Rev. 0, November 2022, 66 pages.
[Public PDF attachment](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/S32K/33599/1/AN13767.pdf).
Retrieved and inspected, including section 3.2. This public copy was accessible
even though the ordinary NXP document download route did not return the PDF.
The equations explicitly use the fundamental harmonic. This document supplies
model structure, not an exact-part friction curve or disc-inertia measurement.

**S2 — AN13902, 3-Phase Sensorless PMSM Motor Control Kit with S32K344
using MBDT Blocks**, Rev. 0, March 2023, 46 pages.
[NXP-authored PDF on a public mirror](https://www.techresearchinfo.com/whitepaper/app-note-mbdt-blocks-for-3-phase-sensorless-pmsm-motor-control.pdf)
and [NXP's corresponding article](https://community.nxp.com/t5/NXP-Model-Based-Design-Tools/3-Phase-Sensorless-PMSM-Motor-Control-Kit-with-S32K344-using/ta-p/1616832).
Inspected. Printed page 2 identifies the Sunrise 42BLY3A78-24110 as the default
motor; printed page 25 refers to AN13767 section 3.2 for the mathematical model.
The mirror is not an NXP-hosted download; authorship and document identity are
visible in the PDF.

**S3 — NXP S32K344 exact-motor parameter profile.**
[M1_params_Sunrise95.txt](https://github.com/nxp-appcodehub/an-mc-pmsm-foc-2sh-s32k344/blob/c619ec789a4f11abeb8d5e5540784ed710731d5f/FreeMASTER_control/MCAT/param_files/M1_params_Sunrise95.txt).
Inspected at commit `c619ec789a4f11abeb8d5e5540784ed710731d5f`.
Published entries include pole pairs 2, Rs 0.192 ohm, Ld 96 microhenry,
Lq 107 microhenry, Ke 0.005872, Kt 0.010614, J 1.2e-5 kg m²,
nominal phase current 6 A, nominal speed 4000 rpm, and configured maximum
speed 5500 rpm. These include application settings; not every entry is an
intrinsic motor property or a universal motor safety limit.

**S4 — NXP identity and parameter conventions.**
[Parameter readme](https://github.com/nxp-appcodehub/an-mc-pmsm-foc-2sh-s32k344/blob/c619ec789a4f11abeb8d5e5540784ed710731d5f/FreeMASTER_control/MCAT/param_files/readme.txt),
[application header](https://github.com/nxp-appcodehub/an-mc-pmsm-foc-2sh-s32k344/blob/c619ec789a4f11abeb8d5e5540784ed710731d5f/src/config/PMSM_appconfig.h),
[MCAT parameter UI](https://github.com/nxp-appcodehub/an-mc-pmsm-foc-2sh-s32k344/blob/c619ec789a4f11abeb8d5e5540784ed710731d5f/FreeMASTER_control/MCAT/src/inner_Parameters.html),
[parameter calculations](https://github.com/nxp-appcodehub/an-mc-pmsm-foc-2sh-s32k344/blob/c619ec789a4f11abeb8d5e5540784ed710731d5f/FreeMASTER_control/MCAT/src/JS_functions/inner_Parameters.js),
and [speed-loop calculations](https://github.com/nxp-appcodehub/an-mc-pmsm-foc-2sh-s32k344/blob/c619ec789a4f11abeb8d5e5540784ed710731d5f/FreeMASTER_control/MCAT/src/JS_functions/inner_SLoop.js).
Inspected. The readme ties the profile to the exact motor part. The UI labels
the 6 A entry as nominal continuous phase current. EMF scaling calculations
include pole pairs and electrical speed. Unit and amplitude conventions must
be reconciled before using Ke or Kt in a different plant representation.
The controller setting DiscMethod=Trapezoidal concerns numerical controller
discretization; it is not evidence of a trapezoidal physical back-EMF waveform.

### MathWorks kit simulation

All following repository files were inspected at commit
`f46489481e1addf54c21d3f5e758395493e1dcab`.

**S5 — Example identity and instructions.**
[Repository README](https://github.com/mathworks/FOC-of-PMSM/blob/f46489481e1addf54c21d3f5e758395493e1dcab/README.md),
[MCSPTE1AK344 example manual](https://github.com/mathworks/FOC-of-PMSM/blob/f46489481e1addf54c21d3f5e758395493e1dcab/MCSPTE1AK344/mcb_nxp_MCSPTE1AK344_example_doc.pdf),
and [hardware initialization identifying Sunrise 42BLY3A78](https://github.com/mathworks/FOC-of-PMSM/blob/f46489481e1addf54c21d3f5e758395493e1dcab/MCSPTE1AK344/Sensorless%20closed%20loop%20speed%20control/s32k344Data.m).
The manual documents both simulation and execution on hardware. It instructs
users to verify/edit motor parameters, so its defaults are not a measurement
certificate.

**S6 — Open-loop motor parameters.**
[mcbOpenLoopData.m](https://github.com/mathworks/FOC-of-PMSM/blob/f46489481e1addf54c21d3f5e758395493e1dcab/MCSPTE1AK344/Open%20loop%20speed%20control/mcbOpenLoopData.m).
Includes Rs 0.192 ohm, Ld 96 microhenry, Lq 107 microhenry,
J 1.2e-5 kg m², B 1e-7 kg m²/s, Ke 2.52 V peak line-to-line/krpm,
and a Kt entry of 0.097 N m/A. PM flux is computed from Ke, pole pairs,
and the line-to-line peak convention.

**S7 — Closed-loop motor parameters.**
[mcbSensorlessData.m](https://github.com/mathworks/FOC-of-PMSM/blob/f46489481e1addf54c21d3f5e758395493e1dcab/MCSPTE1AK344/Sensorless%20closed%20loop%20speed%20control/mcbSensorlessData.m).
Uses the same J, B, Ke and Kt entries as S6, but Rs is 0.244 ohm,
Ld 100 microhenry and Lq 114 microhenry. These files therefore do not supply
one identical parameter set. Their Ke convention also differs from the raw
number in S3. Preserve each source's conventions rather than combining values
silently. A Kt assignment alone does not establish that the plant uses it.

**S8 — Actual simulation plant configuration.**
[MotorFOCSL.slx](https://github.com/mathworks/FOC-of-PMSM/blob/f46489481e1addf54c21d3f5e758395493e1dcab/MCSPTE1AK344/Sensorless%20closed%20loop%20speed%20control/MotorFOCSL.slx)
and [MotorPMSMOpenLoop.slx](https://github.com/mathworks/FOC-of-PMSM/blob/f46489481e1addf54c21d3f5e758395493e1dcab/MCSPTE1AK344/Open%20loop%20speed%20control/MotorPMSMOpenLoop.slx).
Inspected their XML configuration. Both instantiate Interior PMSM with
pole pairs pmsm.p, resistance pmsm.Rs + inverter.R_board,
inductances [pmsm.Ld, pmsm.Lq], flux pmsm.FluxPM, and mechanical parameters
[pmsm.J, pmsm.B, 0]. The model uses flux linkage for its electromagnetic
parameterization; unused mask/default fields are not independent motor data.

**S9 — Mathematical meaning of the MathWorks plant.**
[Interior PMSM documentation](https://www.mathworks.com/help/mcb/ref/interiorpmsm.html).
Defines sinusoidal back-EMF, dq dynamics, electromagnetic torque, and mechanical
parameters including combined motor/load inertia and viscous friction.
This is authority for the block's equations and parameter meanings, not for
the measured physical values of this Sunrise motor.

### Additional NXP exact-motor implementations

**S10 — S32M276 exact-motor parameter profile.**
[M1_params_Sunrise.txt](https://github.com/nxp-appcodehub/an-mc-pmsm-s32m276/blob/05976c5972b899acadf0bf738917245742c186e3/FreeMASTER_control/MCAT/param_files/M1_params_Sunrise.txt)
and [identity readme](https://github.com/nxp-appcodehub/an-mc-pmsm-s32m276/blob/05976c5972b899acadf0bf738917245742c186e3/FreeMASTER_control/MCAT/param_files/readme.txt).
Inspected. Repeats Rs, Ld, Lq and J from S3, but lists Ke 0.00587,
Kt 0.01761 and different application speed/tuning settings. This is additional
published evidence, not permission to mix controller profiles.

**S11 — S32K312 exact-motor parameter profile.**
[M1_params_Sunrise95.txt](https://github.com/nxp-appcodehub/dm-mc-pmsm-foc-s32k312/blob/ed7c41c23d5f2ad1e91ecad80df544a70a6491dd/FreeMASTER_control/MCAT/param_files/M1_params_Sunrise95.txt).
Inspected. Repeats the principal S3 motor parameters and supplies another
application-specific set of tuning values. No friction measurement or explicit
disc-inertia definition was found in this profile.

**S12 — Public NXP MBDT Hall/FOC source archive.**
[NXP employee's source post](https://community.nxp.com/t5/Model-Based-Design-Toolbox-MBDT/S32k344-MBDT-error-for-BLDC-or-PMSM/m-p/1937833/highlight/true)
and [mc_v1.5.0_tppsdk_rtd_P19.zip](https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/mbdt/9382/1/mc_v1.5.0_tppsdk_rtd_P19.zip).
Downloaded without login; inspected its 369-file inventory, Hall/FOC parameter
scripts, readmes, and text-model files for the physical-data questions.
The Hall and FOC headers explicitly list the Sunrise parameters and drive
inertia. Copies of two BSD-3-Clause parameter scripts are in `references/`.
This is S32K344 software, not the S32M244 firmware package; its gains and limits
must not be attributed to S32M244.

### Hardware identity, Hall controller, and manufacturer

**S13 — [NXP BLDC-KIT](https://www.nxp.com/design/design-center/development-boards-and-designs/BLDC-KIT).**
Inspected. Exact motor identity, 24 V/95 W/9000 rpm/6 A/two pole pairs,
Hall sensors, rotor-disc assembly, and separate 12 V/5 A supply.
No disc mass/dimensions or statement about its inclusion in J was found.

**S14 — Hall control reference articles.**
[S32M244](https://community.nxp.com/t5/S32M-Knowledge-Base/S32M244-Hall-sensor-based-6-step-BLDC-motor-control/ta-p/2013453)
and [S32M276](https://community.nxp.com/t5/S32M-Knowledge-Base/S32M276-Hall-sensor-based-6-step-BLDC-motor-control/ta-p/2035021).
Inspected. Establish exact-motor switching tables, Hall sectors, controller
structure, current limitation and fault behavior. They do not supply an
exact-part measured back-EMF curve or mechanical-loss identification.

**S15 — NXP support on exact-motor parameters.**
[PMSM motor parameters](https://community.nxp.com/t5/S32K/PMSM-motor-parameters/m-p/2107952/highlight/true)
and [Important question about motor control](https://community.nxp.com/t5/Model-Based-Design-Toolbox-MBDT/Important-question-about-motor-control/m-p/2305902).
Inspected. NXP directs users to MCAT and identifies the Sunrise MBDT parameter
script. A forum user's proposed numbers are not an NXP confirmation of them.

**S16 — Sunrise manufacturer catalog and discontinued link.**
[Manufacturer 42BLY catalog](https://www.sunrisemotor-cn.com/Brushless-dc-motor-42BLY.html)
and [manufacturer page linked by NXP](https://www.sunrisemotor-cn.com/Product/142451.html).
The latter visibly returned 404. The current catalog lists other variants,
including 42BLY3A78-2445 at 41 W/3000 rpm; these are not the exact 95 W/9000 rpm
-24110 variant. Their constants must not be substituted. No exact-variant
datasheet resolving the remaining questions was located. An archive-index
lookup was inaccessible through the research tool, so archived content was
not inspected.

## Supporting material and access boundaries

- [NXP digital-twin article for MCSPTR2AK396](https://community.nxp.com/t5/NXP-Tech-Blog/End-Node-Virtualization-of-PMSM-FOC-on-MCSPTR2AK396-Motor/ba-p/1870525): inspected; supplies conventional dq/mechanical equations and discusses AMCLIB_EstimRL and AMCLIB_EstimBJ identification. It concerns a different motor; its physical constants do not establish Sunrise data.
- [AN1914](https://www.nxp.com/docs/en/application-note/AN1914.pdf) and [AN12435](https://www.nxp.com/docs/en/application-note/AN12435.pdf): inspected for general BLDC physics and six-step topology. Their generic or different-motor waveform assumptions are not exact Sunrise measurements.
- [NXP inertia/damping discussion](https://community.nxp.com/t5/Motor-Control-and-Smart-Energy/Damping-coefficient-and-moment-of-inertia-of-PMSM/m-p/1206937): inspected; discusses another motor and neglecting friction for PI tuning, which does not establish zero physical friction for Sunrise.
- [NXP MCAT identification discussion](https://community.nxp.com/t5/Motor-Control-and-Smart-Energy/MCAT-unable-to-measure-motor-parameters/m-p/753546): inspected; generic drive-inertia comments do not resolve the exact disc's inclusion.
- [MCAT user guide](https://www.nxp.com/docs/en/user-guide/3PPMSMCDSCUG.pdf) and [AN4912](https://www.nxp.com.cn/docs/en/application-note/AN4912.pdf): inspected for parameter/identification conventions; not exact-part measurements.
- [MCSPTE1AK344](https://www.nxp.com/design/design-center/development-boards-and-designs/MCSPTE1AK344), [MCSPTE1AK116](https://www.nxp.com/design/design-center/development-boards-and-designs/MCSPTE1AK116), and [MCSPTE1AK144](https://www.nxp.com/design/design-center/development-boards-and-designs/MCSPTE1AK144): inspected for kit identity and supported control methods. A kit supporting both FOC and six-step does not determine the exact physical back-EMF waveform.
- S32M24XEVB-SW, including S32M24xEVB_BLDC_6Step_Hall: the NXP download listing required an account; package contents were not inspected. No claim is made that it contains the unresolved mechanical/waveform data. The public S32K344 archive above is a separate, successfully retrieved source.

## Evidence preservation and status

`references/retrieval-manifest.json` records hashes, pinned revisions and archive
member paths for inspected downloaded artifacts. Restricted vendor software and
manuals are referenced at their source URLs rather than redistributed here.
The two copied NXP parameter scripts retain their copyright/SPDX headers and
are accompanied by `references/LICENSE-BSD-3-Clause.txt`.

This search establishes published equations, a kit-specific vendor simulation,
published inertia, and a published example damping setting. It does not establish
an exact-part measured waveform/error bound, measured damping provenance, or
disc inclusion in the listed inertia. Those are unresolved evidence questions,
not demonstrated contradictions in physical measurements.

The older README, REVIEW and SOURCE_CONFORMANCE_AUDIT describe an earlier scalar
plant and certificate. This research addition does not validate those historical
claims or certify the current phase-resolved model. Do not treat a source lookup
as completion of implementation verification.
