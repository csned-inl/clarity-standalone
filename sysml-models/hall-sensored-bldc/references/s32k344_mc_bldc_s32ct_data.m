%% ************************************************************************
% Model         :   MCAT BLDC HALL
% Description   :   Set Parameters for 6step BLDC HALL sensored
% File name     :   s32k344_mc_bldc_s32ct_data.m
% - static configuration of the BLDC HALL application
%% ************************************************************************

% Copyright 2021-2023 NXP
%
% SPDX-License-Identifier: BSD-3-Clause
% The BSD-3-Clause license can be found at 
% https://spdx.org/licenses/BSD-3-Clause.html

%% Sunrise Motor Parameters                      
%Pole-pair number                      = 2 [-]
%Stator resistance                     = 0.192 [Ohms]
%Direct axis inductance                = 0.000096 [H]
%Quadrature axis inductance            = 0.000107 [H]
%Back-EMF constant                     = 0.005872 [V.sec/rad]
%Drive inertia                         = 0.12e-4 [kg.m2]
%Nominal current                       = 6 [A]
%Nominal speed                         = 4000 [rpm]

MBD_ROTATION_DIR_CW                 = uint8(0);
MBD_ROTATION_DIR_CCW                = uint8(1);

MBD_CALIB_TIMER                     = uint16(10000);
MBD_SPEED_UP_CNT                    = single(1000);
MBD_SPEED_DOWN_CNT                  = single(1000);
MBD_APP_OFF_CNT                     = single(5000);

MBD_N_MIN                           = single(400);
MBD_FREEWHEEL_T_LONG                = uint16(100);
MBD_DC_THRESHOLD                    = single(10);
MBD_I_DCB_LIMIT                     = single(4);
MBD_N_NOM                           = single(4000);
MBD_SPEED_LOOP_RAMP_UP              = single(10);
MBD_SPEED_LOOP_RAMP_DOWN            = single(10);
MBD_SPEED_STEP                      = single(200);

MBD_SPEED_LOOP_KP_GAIN              = single(0.001);
MBD_SPEED_LOOP_KI_GAIN              = single(0.0001);
MBD_CTRL_LOOP_LIM_HIGH              = single(92);
MBD_CTRL_LOOP_LIM_LOW               = single(10);

MBD_TORQUE_LOOP_KP_GAIN             = single(0.1);
MBD_TORQUE_LOOP_KI_GAIN             = single(0.03);

MBD_TORQUE_LOOP_MAF                 = single(0.03125);
%% Application scales                    
MBD_I_MAX                           = 31.25;
MBD_U_DCB_MAX                       = 45.0;
MBD_U_DCB                           = 12.0;
MBD_N_MAX                           = 5500.0;
MBD_WEL_MAX                         = 1151.92;
MBD_E_MAX                           = 6.765;

%% Application Fault Triggers
MBD_U_DCB_UNDERVOLTAGE              = single(9);
MBD_I_DCB_OVERCURRENT               = single(5);
MBD_U_DCB_OVERVOLTAGE               = single(18);
MBD_LED_FLASHING                    = 250 * 2;

%% Application config
% PWM period in ticks: fEMIOS / emios_global_prescaler / fPWM = 160MHz / 1 / 20kHz = 8000
MBD_APP_PWM_PERIOD                  = 8000;
MBD_APP_PWM_MASK                    = uint32(0xE00);

%% Filters
MBD_uDcbFilter_fltLambda            = 1.0 / 8.0;
MBD_iABCFilter_fltLambda            = 1/16;

%% Application States
MBD_APP_INIT                        = uint8(0);
MBD_APP_CALIB                       = uint8(1);
MBD_APP_ALIGNMENT                   = uint8(2);
MBD_APP_START                       = uint8(3);
MBD_APP_RUN                         = uint8(4);
MBD_APP_STOP                        = uint8(5);
MBD_APP_FAULT                       = uint8(6);