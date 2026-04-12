# modbus/rs485/water_tester_points.py
# RS485 Water Tester Modbus RTU register mapping for PoolAIssistant
#
# NOTE: This is a placeholder/template register definition.
# The actual register addresses should be updated when the device is acquired
# and the Modbus documentation is available.
#
# Format matches the existing Ezetrol/BAYROL/DULCOPOOL point definitions:
# - "label": Point identifier for database storage
# - "manual": Register address (manual-style numbering, 40001+ for holding registers)
# - "type": Data type ("f32", "u16", "u32", "str")
# - "count": Number of 16-bit registers to read
# - "reg_type": "holding" or "input" (default: "holding")
# - "scale": Optional scaling factor
# - "word_order": "AB" (default) or "BA" for 32-bit values
#
# Common water tester metrics:
# - TDS (Total Dissolved Solids) - ppm
# - EC (Electrical Conductivity) - uS/cm or mS/cm
# - Salinity - ppt
# - Temperature - C or F (if sensor has temp compensation)

POINTS = [
    # -----------------------------
    # Device Information (RO)
    # -----------------------------
    # Many water testers expose device ID/model info
    {"label": "WaterTest_DeviceModel",   "manual": 40001, "type": "u16", "count": 1, "reg_type": "holding"},
    {"label": "WaterTest_FirmwareVer",   "manual": 40002, "type": "u16", "count": 1, "reg_type": "holding"},

    # -----------------------------
    # Measurements (RO)
    # -----------------------------
    # TDS (Total Dissolved Solids)
    {"label": "WaterTest_TDS",           "manual": 40101, "type": "u16", "count": 1, "reg_type": "holding"},
    # Units: ppm (parts per million)

    # EC (Electrical Conductivity)
    {"label": "WaterTest_EC",            "manual": 40102, "type": "u16", "count": 1, "reg_type": "holding"},
    # Units: uS/cm, may need scaling (e.g., scale: 0.1 for raw value 1500 = 150.0 uS/cm)

    # Salinity
    {"label": "WaterTest_Salinity",      "manual": 40103, "type": "u16", "count": 1, "reg_type": "holding"},
    # Units: ppt (parts per thousand)

    # Temperature (if device has temp compensation)
    {"label": "WaterTest_Temperature",   "manual": 40104, "type": "u16", "count": 1, "reg_type": "holding", "scale": 0.1},
    # Units: Celsius, scale 0.1 means raw 250 = 25.0 C

    # Additional common measurements (may vary by device)
    {"label": "WaterTest_ORP",           "manual": 40105, "type": "u16", "count": 1, "reg_type": "holding"},
    # Units: mV

    {"label": "WaterTest_pH",            "manual": 40106, "type": "u16", "count": 1, "reg_type": "holding", "scale": 0.01},
    # Units: pH, scale 0.01 means raw 725 = 7.25 pH

    # -----------------------------
    # Status/Calibration (RO)
    # -----------------------------
    {"label": "WaterTest_Status",        "manual": 40201, "type": "u16", "count": 1, "reg_type": "holding"},
    # Bit flags: b0=sensor OK, b1=cal needed, etc.

    {"label": "WaterTest_CalibrationAge", "manual": 40202, "type": "u16", "count": 1, "reg_type": "holding"},
    # Days since last calibration

    # -----------------------------
    # Configuration (RW) - optional
    # -----------------------------
    # Measurement interval (if configurable)
    {"label": "WaterTest_MeasInterval",  "manual": 40301, "type": "u16", "count": 1, "reg_type": "holding"},
    # Seconds between measurements

    # Temp compensation mode
    {"label": "WaterTest_TempCompMode",  "manual": 40302, "type": "u16", "count": 1, "reg_type": "holding"},
    # 0=Auto, 1=Manual, 2=Disabled
]

# -----------------------------
# Point Groups for UI Display
# -----------------------------
# These groups can be used to organize readings in the UI

MEASUREMENT_LABELS = [
    "WaterTest_TDS",
    "WaterTest_EC",
    "WaterTest_Salinity",
    "WaterTest_Temperature",
    "WaterTest_ORP",
    "WaterTest_pH",
]

STATUS_LABELS = [
    "WaterTest_Status",
    "WaterTest_CalibrationAge",
]

INFO_LABELS = [
    "WaterTest_DeviceModel",
    "WaterTest_FirmwareVer",
]

# -----------------------------
# Validation Ranges
# -----------------------------
# Used to filter out invalid readings

VALID_RANGES = {
    "WaterTest_TDS": (0.0, 50000.0),       # ppm
    "WaterTest_EC": (0.0, 100000.0),       # uS/cm
    "WaterTest_Salinity": (0.0, 50.0),     # ppt
    "WaterTest_Temperature": (-10.0, 60.0), # Celsius
    "WaterTest_ORP": (-500.0, 1200.0),     # mV
    "WaterTest_pH": (0.0, 14.0),           # pH
}


def get_point_by_label(label: str) -> dict:
    """Get point definition by label."""
    for p in POINTS:
        if p.get("label") == label:
            return p
    return {}


def get_measurement_points() -> list:
    """Get all measurement point definitions."""
    return [p for p in POINTS if p.get("label") in MEASUREMENT_LABELS]


def validate_reading(label: str, value: float) -> bool:
    """
    Validate a reading against known valid ranges.
    Returns True if valid, False if out of range.
    """
    if value is None:
        return True
    range_def = VALID_RANGES.get(label)
    if range_def:
        vmin, vmax = range_def
        if value < vmin or value > vmax:
            return False
    return True
