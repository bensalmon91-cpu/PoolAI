# walchem_modbus_points.py
# Walchem WebMaster ONE Modbus TCP register mapping for PoolAIssistant logger
# Source: WebMaster ONE Modbus TCP/IP Option Manual (180422)
#
# TODO: VERIFICATION NEEDED
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# This implementation is based on simulator protocol definitions only.
# Before production use, verify against:
# 1. Official Walchem WebMaster ONE Modbus TCP/IP Option Manual
# 2. Real Walchem WebMaster hardware
#
# Items to verify:
# - Register addresses (documentation uses 1-based addressing)
# - Float Inverse word order (BA - low word first)
# - Channel mappings for your specific installation
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Protocol details:
# - FC03 (holding registers) for all data
# - Float Inverse word order (BA) for 32-bit values
# - Supports multi-register reads
# - Up to 4 direct sensor inputs (SI1-SI4) for pH, ORP, conductivity, etc.
# - Up to 8 analog inputs (AI1-AI8) for 4-20mA sensors

POINTS = [
    # Sensor Input Calibrated Values (Float32, BA word order)
    {"label": "SI1_MeasuredValue", "manual": 43001, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI2_MeasuredValue", "manual": 43003, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI3_MeasuredValue", "manual": 43005, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI4_MeasuredValue", "manual": 43007, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},

    # Sensor Input Temperature Values (Float32, BA word order)
    {"label": "SI1_Temperature", "manual": 43049, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI2_Temperature", "manual": 43051, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI3_Temperature", "manual": 43053, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI4_Temperature", "manual": 43055, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},

    # Analog Input Scaled Values (4-20mA inputs, Float32, BA word order)
    {"label": "AI1_MeasuredValue", "manual": 43097, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "AI2_MeasuredValue", "manual": 43099, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "AI3_MeasuredValue", "manual": 43101, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "AI4_MeasuredValue", "manual": 43103, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "AI5_MeasuredValue", "manual": 43105, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "AI6_MeasuredValue", "manual": 43107, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "AI7_MeasuredValue", "manual": 43109, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "AI8_MeasuredValue", "manual": 43111, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},

    # Sensor Input Status (u16)
    {"label": "SI1_Status", "manual": 42002, "type": "u16", "count": 1, "reg_type": "holding"},
    {"label": "SI2_Status", "manual": 42004, "type": "u16", "count": 1, "reg_type": "holding"},
    {"label": "SI3_Status", "manual": 42006, "type": "u16", "count": 1, "reg_type": "holding"},
    {"label": "SI4_Status", "manual": 42008, "type": "u16", "count": 1, "reg_type": "holding"},

    # Sensor Input Alarm Setpoints (Float32, BA word order)
    # SI1 (typically pH)
    {"label": "SI1_LowLowAlarm", "manual": 60641, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI1_LowAlarm", "manual": 60643, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI1_HighAlarm", "manual": 60645, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI1_HighHighAlarm", "manual": 60647, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},

    # SI2 (typically ORP)
    {"label": "SI2_LowLowAlarm", "manual": 60671, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI2_LowAlarm", "manual": 60673, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI2_HighAlarm", "manual": 60675, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
    {"label": "SI2_HighHighAlarm", "manual": 60677, "type": "f32", "count": 2, "reg_type": "holding", "word_order": "BA"},
]
