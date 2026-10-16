%% ************************************************************************
% Model         :   MCAT PMSM FOC
% Description   :   Set Parameters for PMSM Field Oriented Control
% File name     :   s32k344_mc_pmsm_2sh_s32ct_data.m
% - static configuration of the PMSM FOC application
%% ************************************************************************

% Copyright 2021-2023 NXP
%
% SPDX-License-Identifier: BSD-3-Clause
% The BSD-3-Clause license can be found at 
% https://spdx.org/licenses/BSD-3-Clause.html

%% Sunrise Motor Parameters                      
% Pole-pair number                      = 2 [-]
% Stator resistance                     = 0.192 [Ohms]
% Direct axis inductance                = 0.000096 [H]
% Quadrature axis inductance            = 0.000107 [H]
% Back-EMF constant                     = 0.005872 [V.sec/rad]
% Drive inertia                         = 0.12e-4 [kg.m2]
% Nominal current                       = 6 [A]
% Nominal speed                         = 4000 [rpm]

MBD_MOTOR_PP                        = 2.0;
%#define MOTOR_PP_GAIN                   FRAC32(0.5)
MBD_MOTOR_PP_GAIN                   = double(0.5);
MBD_MOTOR_PP_SHIFT                  = 2;

%% Application scales                    
MBD_I_MAX                           = 31.25;
MBD_U_DCB_MAX                       = 45.0;
MBD_U_DCB                           = 12.0;
MBD_N_MAX                           = 5500.0;
MBD_WEL_MAX                         = 1151.92;
MBD_E_MAX                           = 6.765;

%% Application Fault Triggers
MBD_U_DCB_TRIP                      = 17.0;
MBD_U_DCB_UNDER                     = 8.0;
MBD_U_DCB_OVER                      = 18.0;
MBD_I_PH_OVER                       = 7.0;
MBD_I_DCB_OVER                      = 8.3;
MBD_TEMP_OVER                       = 110.0;

%% DC Bus voltage IIR1 filter constants  
%Cut-off frequency                     = 100 [Hz]
%Sample time                           = 0.0001 [sec]
%----------------------------------------------------------------------
MBD_UDCB_IIR_B0                     = 0.030459027951421222;
MBD_UDCB_IIR_B1                     = 0.030459027951421222;
MBD_UDCB_IIR_A1                     = -0.9390819440971575;
%Mechanical Alignment                  
MBD_ALIGN_VOLTAGE                   = 0.5;
MBD_ALIGN_DURATION                  = 10000;
%%Application params
MBD_ALIGN_D_FACTOR                  = 0.9;

%% Current Loop Control                  
%----------------------------------------------------------------------
%Loop Bandwidth                        = 150 [Hz]
%Loop Attenuation                      = 1 [-]
%Loop sample time                      = 0.0001 [sec]
%----------------------------------------------------------------------
%Current Controller Output Limit       
MBD_CLOOP_LIMIT                     = 0.9;
%D-axis Controller - Recurrent type    
MBD_D_CC1SC                         = 0.4585598906144692;
MBD_D_CC2SC                         = -0.36381168836401134;
%Q-axis Controller - Recurrent type    
MBD_Q_CC1SC                         = 0.5331032114140437;
MBD_Q_CC2SC                         = -0.4274984443223876;

%% Speed Loop Control                    
%----------------------------------------------------------------------
%Loop Bandwidth                        = 1 [Hz]
%Loop Attenuation                      = 1 [-]
%Loop sample time                      = 0.001 [sec]
%----------------------------------------------------------------------
%Speed Controller - Parallel type      
MBD_SPEED_PI_PROP_GAIN              = 0.028414631123480322;
MBD_SPEED_PI_INTEG_GAIN             = 0.00008926719639198968;
MBD_SPEED_LOOP_HIGH_LIMIT           = 6.0;
MBD_SPEED_LOOP_LOW_LIMIT            = -6.0;

MBD_SPEED_RAMP_UP                   = 0.62832;
MBD_SPEED_RAMP_DOWN                 = 0.62832;

MBD_SPEED_LOOP_CNTR                 = 10;

MBD_POSPE_SPEED_FILTER_MA_LAMBDA    = 0.8;
MBD_MAX_TH_DIF_OPEN_ESTIM           = 0.01;
MBD_SENSORLESS_CNT                  = uint16(10000);
%% Position & Speed Sensors Module       
%Loop sample time                      = 0.0001 [sec]
%----------------------------------------------------------------------
%Encoder Loop Bandwidth                = 100 [Hz]
%Encoder Loop Attenuation              = 1 [-]
MBD_POSPE_ENC_TO_CC1                = 1276.376270238096;
MBD_POSPE_ENC_TO_CC2                = -1236.8978526337387;
MBD_POSPE_ENC_TO_INTEG_GAIN         = 0.00005;
MBD_ENC_PULSES                      = 1024;

%% Sensorless DQ BEMF Observer and Tracking Observer
%----------------------------------------------------------------------
%Loop Bandwidth                        = 150 [Hz]
%Loop Attenuation                      = 1 [-]
%Loop sample time                      = 0.0001 [sec]
%----------------------------------------------------------------------
%DQ Bemf - plant coefficients          
MBD_I_Gain                          = 0.8181818181818181;
MBD_U_Gain                          = 0.4734848484848485;
MBD_E_Gain                          = 0.4734848484848485;
MBD_WI_Gain                         = 0.00005066287878787879;

%DQ Bemf - PI controller parameters    
MBD_BEMF_DQ_CC1_GAIN                = 0.4585598906144692;
MBD_BEMF_DQ_CC2_GAIN                = -0.36381168836401134;

%Tracking Observer - PI controller parameters
MBD_TO_CC1SC                        = 378.7676472229712;
MBD_TO_CC2SC                        = -375.21458963857907;
%Tracking Observer - Integrator        
MBD_TO_THETA_GAIN                   = 0.00005;

%Observer speed output filter          

%Open loop start-up                    
MBD_OL_START_RAMP_INC               = 0.20944;
MBD_OL_START_I                      = 3.0;
MBD_CL_START_RAMP_INC               = 0.62832;
MBD_MERG_SPEED_1_TRH                = 300.0;
MBD_MERG_SPEED_2_TRH                = 600.0;
MBD_TRACKING_LOW_LIM                = ((2 * pi * MBD_MOTOR_PP) * MBD_MERG_SPEED_1_TRH)/60;
MBD_TRACKING_HIGH_LIM               = ((2 * pi * MBD_MOTOR_PP) * MBD_MERG_SPEED_2_TRH)/60;
MBD_SPEED_RPM_INC                   = 200;
MBD_SPEED_RPM_DEC                   = 200;
MBD_SPEED_UP_CNT                    = 1000;               
MBD_SPEED_DOWN_CNT                  = 1000;
MBD_BTN_FACTOR                      = 0.8;
MBD_SPEED_LIM_RAD_BTN               = MBD_WEL_MAX * MBD_BTN_FACTOR;
MBD_APP_OFF_CNT                     = 5000;
MBD_SPEED_RAD_INC = single(MBD_SPEED_RPM_INC/MBD_N_MAX) * MBD_WEL_MAX;
MBD_SPEED_RAD_DEC = single(MBD_SPEED_RPM_DEC/MBD_N_MAX) * MBD_WEL_MAX;


%% Control Structure Module - Scalar Control
MBD_SCALAR_VHZ_FACTOR_GAIN          = 0.03084422797120932;
MBD_SCALAR_INTEG_GAIN               = 0.008333333333;
MBD_SCALAR_INTEG_SHIFT              = 0;
MBD_SCALAR_RAMP_UP                  = 0.06283;
MBD_SCALAR_RAMP_DOWN                = 0.06283;

%% FreeMASTER Scale Variables            
%----------------------------------------------------------------------
%Note: Scaled at input = 1000          
%----------------------------------------------------------------------
MBD_FM_SPEED_RAD_MEC_SCALE          = 1000;
MBD_FM_SPEED_RPM_EL_SCALE           = 9549;
MBD_FM_SPEED_RPM_MEC_SCALE          = 4775;
MBD_FM_POSITION_DEG_SCALE           = 57296;

%% Application config
%%*****************************************************************************
% Define Motor with or without Encoder sensor

% ENCODER  0    PM motor is NOT equipped with Encoder sensor, motor position/speed is estimated only by eBEMF observer
% ENCODER  1    PM motor is equipped with Encoder sensor, motor position/speed can either be estimated by eBEMF observer
%           or obtained by Encoder sensor. To switch between Sensorless and Encoder mode use switchSensor variable.

% Note        Default PM motor of the MTRDEVKSPNK144 (LINIX 45ZWN24-40) is NOT equipped with Encoder sensor,
%           thus ENCODER 0 is used as default for MTRDEVKSPNK144

MBD_ENCODER                         = 0;

% PWM period in ticks: fEMIOS / emios_global_prescaler / fPWM = 160MHz / 1 / 20kHz = 8000
MBD_APP_PWM_PERIOD                  = 8000;
MBD_APP_PWM_MASK                    = uint32(0xE00);

% Modulus counter buffered (up/down) A1 compare value
MBD_APP_MC_A1                       = MBD_APP_PWM_PERIOD + 1;
MBD_APP_MC_A1_trigger               = 2 * MBD_APP_MC_A1;
% Number of ticks per half of a PWM period used for duty cycle calculation
MBD_APP_PWM_PERIOD_HALF             = (MBD_APP_PWM_PERIOD / 2) + 1;

MBD_APP_OPWMB_A_DC_0                = 1;
MBD_APP_OPWMB_B_DC_0                = MBD_APP_MC_A1;

MBD_LED_FLASHING                    = 1250 * 2;
MBD_FOC_TIMEOUT                     = 10000;

%% Filters
MBD_uDcbFilter_fltLambda            = 1.0 / 8.0;
MBD_iABCFilter_fltLambda            = 1/16;

%% Application States
MBD_init                              = uint8(0);
MBD_fault                             = uint8(1);
MBD_ready                             = uint8(2);
MBD_calib                             = uint8(3);
MBD_align                             = uint8(4);
MBD_run                               = uint8(5);

%% Application Events
MBD_e_fault                             = uint8(0);
MBD_e_fault_clear                       = uint8(1);
MBD_e_init                              = uint8(2);
MBD_e_init_done                         = uint8(3);
MBD_e_ready                             = uint8(4);
MBD_e_app_on                            = uint8(5);
MBD_e_calib                             = uint8(6);
MBD_e_calib_done                        = uint8(7);
MBD_e_align                             = uint8(8);
MBD_e_align_done                        = uint8(9);
MBD_e_run                               = uint8(10);
MBD_e_app_off                           = uint8(11);

%% Application Modes
MBD_force_mode                          = uint8(0);
MBD_tracking_mode                       = uint8(1);
MBD_sensorless_mode                     = uint8(2);