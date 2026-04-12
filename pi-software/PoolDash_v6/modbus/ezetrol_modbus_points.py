# ezetrol_modbus_points.py
# Ezetrol Touch Modbus TCP register mapping (FULL) for PoolAIssistant logger
#
# Source: Ezetrol touch Interfaces 4.4.2 reference list (400001..401108)
#
# NOTE:
# - "manual" uses the 400001-style numbering shown in the manual.
# - "type":
#     - "str" = ASCII string held in 16-bit registers (2 chars per register)
#     - "f32" = 32-bit float (2 registers)
#     - "u16" = 16-bit unsigned (1 register)
#     - "u32" = 32-bit unsigned (2 registers)
# - "count" is number of 16-bit registers to read for that point.

POINTS = [
    # -----------------------------
    # [400001-400099] Info area (RO)
    # -----------------------------
    {"label": "SystemName",      "manual": 400001, "type": "str", "count": 20},
    {"label": "SoftwareVersion", "manual": 400011, "type": "str", "count": 10},
    {"label": "CurrentDate",     "manual": 400016, "type": "str", "count": 10},
    {"label": "CurrentTime",     "manual": 400021, "type": "str", "count": 6},
    {"label": "SerialNumber",    "manual": 400024, "type": "str", "count": 16},

    # -----------------------------------
    # [400100-400299] Measurements (RO)
    # -----------------------------------
    # Ch.1 Chlorine
    {"label": "Chlorine_MeasuredValue", "manual": 400100, "type": "f32", "count": 2},
    {"label": "Chlorine_Unit",          "manual": 400102, "type": "str", "count": 10},
    {"label": "Chlorine_LowerRange",    "manual": 400107, "type": "f32", "count": 2},
    {"label": "Chlorine_UpperRange",    "manual": 400109, "type": "f32", "count": 2},
    {"label": "Chlorine_Setpoint",      "manual": 400111, "type": "f32", "count": 2},
    {"label": "Chlorine_Yout",          "manual": 400113, "type": "f32", "count": 2},

    # Ch.2 pH
    {"label": "pH_MeasuredValue", "manual": 400115, "type": "f32", "count": 2},
    {"label": "pH_Unit",          "manual": 400117, "type": "str", "count": 10},
    {"label": "pH_LowerRange",    "manual": 400122, "type": "f32", "count": 2},
    {"label": "pH_UpperRange",    "manual": 400124, "type": "f32", "count": 2},
    {"label": "pH_Setpoint",      "manual": 400126, "type": "f32", "count": 2},
    {"label": "pH_Yout",          "manual": 400128, "type": "f32", "count": 2},

    # Ch.3 ORP
    {"label": "ORP_MeasuredValue", "manual": 400130, "type": "f32", "count": 2},
    {"label": "ORP_Unit",          "manual": 400132, "type": "str", "count": 10},
    {"label": "ORP_LowerRange",    "manual": 400137, "type": "f32", "count": 2},
    {"label": "ORP_UpperRange",    "manual": 400139, "type": "f32", "count": 2},
    # Manual marks 400141/400143 as "--" (4 bytes each). Keep raw u32.
    {"label": "ORP_Reserved_400141", "manual": 400141, "type": "u32", "count": 2},
    {"label": "ORP_Reserved_400143", "manual": 400143, "type": "u32", "count": 2},

    # Ch.4 Cl2/CLN/Conductivity (manual notes "not yet available" but registers exist)
    {"label": "Ch4_MeasuredValue", "manual": 400145, "type": "f32", "count": 2},
    {"label": "Ch4_Unit",          "manual": 400147, "type": "str", "count": 10},
    {"label": "Ch4_LowerRange",    "manual": 400152, "type": "f32", "count": 2},
    {"label": "Ch4_UpperRange",    "manual": 400154, "type": "f32", "count": 2},
    {"label": "Ch4_Setpoint",      "manual": 400156, "type": "f32", "count": 2},
    {"label": "Ch4_Yout",          "manual": 400158, "type": "f32", "count": 2},

    # Ch.5 Temperature
    {"label": "Temp_MeasuredValue", "manual": 400160, "type": "f32", "count": 2},
    {"label": "Temp_Unit",          "manual": 400162, "type": "str", "count": 10},
    {"label": "Temp_LowerRange",    "manual": 400167, "type": "f32", "count": 2},
    {"label": "Temp_UpperRange",    "manual": 400169, "type": "f32", "count": 2},
    {"label": "Temp_Reserved_400171", "manual": 400171, "type": "u32", "count": 2},
    {"label": "Temp_Reserved_400173", "manual": 400173, "type": "u32", "count": 2},

    # -----------------------------------
    # [400300-400399] Status messages (RO)
    # -----------------------------------
    {"label": "Status_LimitContactStates", "manual": 400300, "type": "u16", "count": 1},
    {"label": "Status_DigitalInputs",      "manual": 400301, "type": "u16", "count": 1},
    {"label": "Status_RelayOutputs_K1_8",  "manual": 400302, "type": "u16", "count": 1},
    {"label": "Status_Reserved_400303",    "manual": 400303, "type": "u16", "count": 1},

    {"label": "Status_Mode_Controller1_Chlorine", "manual": 400304, "type": "u16", "count": 1},
    {"label": "Status_Mode_Controller2_pH",       "manual": 400305, "type": "u16", "count": 1},
    {"label": "Status_Reserved_400306",           "manual": 400306, "type": "u16", "count": 1},
    {"label": "Status_Mode_Controller4_Ch4",      "manual": 400307, "type": "u16", "count": 1},
    {"label": "Status_Reserved_400308",           "manual": 400308, "type": "u16", "count": 1},

    # Error codes (bitfields, RO)
    {"label": "ErrorCode_Chlorine",     "manual": 400310, "type": "u32", "count": 2},
    {"label": "ErrorCode_pH",           "manual": 400314, "type": "u32", "count": 2},
    {"label": "ErrorCode_ORP",          "manual": 400318, "type": "u32", "count": 2},
    {"label": "ErrorCode_TotalChlorine","manual": 400322, "type": "u32", "count": 2},
    {"label": "ErrorCode_Temperature",  "manual": 400326, "type": "u32", "count": 2},

    # -----------------------------------------
    # [401000-401049] Controller parameters (RW)
    # -----------------------------------------
    # Ch.1 Chlorine
    {"label": "Ctrl1_Chlorine_Setpoint_W", "manual": 401000, "type": "f32", "count": 2},
    {"label": "Ctrl1_Chlorine_Xp",         "manual": 401002, "type": "f32", "count": 2},
    {"label": "Ctrl1_Chlorine_Tn",         "manual": 401004, "type": "f32", "count": 2},

    # Ch.2 pH
    {"label": "Ctrl2_pH_Setpoint_W", "manual": 401006, "type": "f32", "count": 2},
    {"label": "Ctrl2_pH_Xp",         "manual": 401008, "type": "f32", "count": 2},
    {"label": "Ctrl2_pH_Tn",         "manual": 401010, "type": "f32", "count": 2},

    # (401012/401014/401016 are "---" in the manual snippet)
    {"label": "Ctrl_Reserved_401012", "manual": 401012, "type": "u32", "count": 2},
    {"label": "Ctrl_Reserved_401014", "manual": 401014, "type": "u32", "count": 2},

    # Ch.4 Cl2/CLN/Conductivity
    {"label": "Ctrl4_Ch4_Setpoint_W", "manual": 401018, "type": "f32", "count": 2},
    {"label": "Ctrl4_Ch4_Xp",         "manual": 401020, "type": "f32", "count": 2},
    {"label": "Ctrl4_Ch4_Tn",         "manual": 401022, "type": "f32", "count": 2},

    # -----------------------------------------
    # [401050-401149] Limit value parameters (RW)
    # -----------------------------------------
    # Ch.1 Chlorine
    {"label": "Lim1_Chlorine_Min1", "manual": 401050, "type": "f32", "count": 2},
    {"label": "Lim1_Chlorine_Max1", "manual": 401052, "type": "f32", "count": 2},
    {"label": "Lim1_Chlorine_Hys1", "manual": 401054, "type": "f32", "count": 2},
    {"label": "Lim1_Chlorine_Min2", "manual": 401056, "type": "f32", "count": 2},
    {"label": "Lim1_Chlorine_Max2", "manual": 401058, "type": "f32", "count": 2},
    {"label": "Lim1_Chlorine_Hys2", "manual": 401060, "type": "f32", "count": 2},

    # Ch.2 pH
    {"label": "Lim2_pH_Min1", "manual": 401062, "type": "f32", "count": 2},
    {"label": "Lim2_pH_Max1", "manual": 401064, "type": "f32", "count": 2},
    {"label": "Lim2_pH_Hys1", "manual": 401066, "type": "f32", "count": 2},
    {"label": "Lim2_pH_Min2", "manual": 401068, "type": "f32", "count": 2},
    {"label": "Lim2_pH_Max2", "manual": 401070, "type": "f32", "count": 2},
    {"label": "Lim2_pH_Hys2", "manual": 401072, "type": "f32", "count": 2},

    # Ch.3 ORP
    {"label": "Lim3_ORP_Min1", "manual": 401074, "type": "f32", "count": 2},
    {"label": "Lim3_ORP_Max1", "manual": 401076, "type": "f32", "count": 2},
    {"label": "Lim3_ORP_Hys1", "manual": 401078, "type": "f32", "count": 2},
    {"label": "Lim3_ORP_Min2", "manual": 401080, "type": "f32", "count": 2},
    {"label": "Lim3_ORP_Max2", "manual": 401082, "type": "f32", "count": 2},
    {"label": "Lim3_ORP_Hys2", "manual": 401084, "type": "f32", "count": 2},

    # Ch.4
    {"label": "Lim4_Ch4_Min1", "manual": 401086, "type": "f32", "count": 2},
    {"label": "Lim4_Ch4_Max1", "manual": 401088, "type": "f32", "count": 2},
    {"label": "Lim4_Ch4_Hys1", "manual": 401090, "type": "f32", "count": 2},
    {"label": "Lim4_Ch4_Min2", "manual": 401092, "type": "f32", "count": 2},
    {"label": "Lim4_Ch4_Max2", "manual": 401094, "type": "f32", "count": 2},
    {"label": "Lim4_Ch4_Hys2", "manual": 401096, "type": "f32", "count": 2},

    # Ch.5 Temperature
    {"label": "Lim5_Temp_Min1", "manual": 401098, "type": "f32", "count": 2},
    {"label": "Lim5_Temp_Max1", "manual": 401100, "type": "f32", "count": 2},
    {"label": "Lim5_Temp_Hys1", "manual": 401102, "type": "f32", "count": 2},
    {"label": "Lim5_Temp_Min2", "manual": 401104, "type": "f32", "count": 2},
    {"label": "Lim5_Temp_Max2", "manual": 401106, "type": "f32", "count": 2},
    {"label": "Lim5_Temp_Hys2", "manual": 401108, "type": "f32", "count": 2},
]
