"""
Alarm code to human-readable description mapping
Maps technical alarm codes to user-friendly messages with severity and actions

Based on Ezetrol Modbus Register Documentation v4.4.2
"""

# ErrorCode bit definitions (same for all channels per Ezetrol docs)
# Registers: 400310 (Cl), 400314 (pH), 400318 (ORP), 400322 (TotalCl), 400326 (Temp)
ERRORCODE_BITS = {
    0:  {"name": "Zero Point Calibration", "severity": "warning"},
    1:  {"name": "DPD Calibration", "severity": "warning"},
    2:  {"name": "pH7 Calibration", "severity": "warning"},
    3:  {"name": "pHX Calibration", "severity": "warning"},
    4:  {"name": "Calibration Error", "severity": "warning"},
    5:  {"name": "Offset Calibration", "severity": "warning"},
    7:  {"name": "Cell Error", "severity": "critical"},
    8:  {"name": "Factory Calibration Error", "severity": "critical"},
    11: {"name": "Setpoint Error", "severity": "warning"},
    12: {"name": "Limit Value Error", "severity": "warning"},
    13: {"name": "Peak Chlorination Error", "severity": "warning"},
    14: {"name": "Combined Chlorine Error", "severity": "warning"},
    15: {"name": "Overfeed - Max Dosing Time", "severity": "critical"},
    16: {"name": "Auto Tune Error", "severity": "warning"},
    18: {"name": "Temperature Error", "severity": "warning"},
    19: {"name": "Tank Empty", "severity": "critical"},
    20: {"name": "No Sample Water", "severity": "critical"},
    23: {"name": "mA Output 1 Load Error", "severity": "critical"},
    24: {"name": "mA Output 2 Load Error", "severity": "critical"},
    25: {"name": "mA Output 3 Load Error", "severity": "critical"},
    26: {"name": "mA Output 4 Load Error", "severity": "critical"},
    27: {"name": "Dosage Analog Error", "severity": "critical"},
    28: {"name": "Flocculation Error", "severity": "warning"},
    29: {"name": "Peak Chlorination Error", "severity": "warning"},
    30: {"name": "Analog Hardware Error", "severity": "critical"},
    31: {"name": "Data Storage Error", "severity": "warning"},
}

# Channel names for ErrorCode registers
ERRORCODE_CHANNELS = {
    "ErrorCode_Chlorine": "Chlorine",
    "ErrorCode_pH": "pH",
    "ErrorCode_ORP": "ORP",
    "ErrorCode_TotalChlorine": "Total Chlorine",
    "ErrorCode_Temperature": "Temperature",
}

# Limit contact descriptions (generic - meaning depends on wiring)
LIMIT_CONTACT_DESCRIPTIONS = {
    0: "Limit Contact 1",
    1: "Limit Contact 2",
    2: "Limit Contact 3",
    3: "Limit Contact 4",
    4: "Limit Contact 5",
    5: "Limit Contact 6",
    6: "Limit Contact 7",
    7: "Limit Contact 8",
}

ALARM_DESCRIPTIONS = {
    # Limit Contact States (400300)
    # These are generic - actual meaning depends on how they're wired
    "Status_LimitContactStates:b0": {
        "name": "Limit Contact 1 Active",
        "severity": "warning",
        "description": "Limit contact 1 has been triggered",
        "action": "Check the equipment connected to limit contact 1.",
    },
    "Status_LimitContactStates:b1": {
        "name": "Limit Contact 2 Active",
        "severity": "warning",
        "description": "Limit contact 2 has been triggered",
        "action": "Check the equipment connected to limit contact 2.",
    },
    "Status_LimitContactStates:b2": {
        "name": "Limit Contact 3 Active",
        "severity": "warning",
        "description": "Limit contact 3 has been triggered",
        "action": "Check the equipment connected to limit contact 3.",
    },
    "Status_LimitContactStates:b3": {
        "name": "Limit Contact 4 Active",
        "severity": "warning",
        "description": "Limit contact 4 has been triggered",
        "action": "Check the equipment connected to limit contact 4.",
    },
    "Status_LimitContactStates:b4": {
        "name": "Limit Contact 5 Active",
        "severity": "warning",
        "description": "Limit contact 5 has been triggered",
        "action": "Check the equipment connected to limit contact 5.",
    },
    "Status_LimitContactStates:b5": {
        "name": "Limit Contact 6 Active",
        "severity": "warning",
        "description": "Limit contact 6 has been triggered",
        "action": "Check the equipment connected to limit contact 6.",
    },
    "Status_LimitContactStates:b6": {
        "name": "Limit Contact 7 Active",
        "severity": "warning",
        "description": "Limit contact 7 has been triggered",
        "action": "Check the equipment connected to limit contact 7.",
    },
    "Status_LimitContactStates:b7": {
        "name": "Limit Contact 8 Active",
        "severity": "warning",
        "description": "Limit contact 8 has been triggered",
        "action": "Check the equipment connected to limit contact 8.",
    },

    # Digital Input (400301)
    "Status_DigitalInputs:b0": {
        "name": "Sample Water Stop",
        "severity": "critical",
        "description": "Sample water flow has stopped (DI1)",
        "action": "Check sample water pump and flow. Dosing may be stopped.",
    },
}

SEVERITY_COLORS = {
    "info": "#0b5bd3",      # Blue
    "warning": "#ff9800",   # Orange
    "critical": "#b00020",  # Red
}

SEVERITY_ICONS = {
    "info": "i",
    "warning": "!",
    "critical": "X",
}


def get_alarm_info(label):
    """
    Get human-readable alarm information

    Args:
        label: Technical alarm label (e.g., "ErrorCode_Chlorine:b7")

    Returns:
        dict with name, severity, description, action, color, icon
    """
    # Check static descriptions first
    if label in ALARM_DESCRIPTIONS:
        info = ALARM_DESCRIPTIONS[label].copy()
        severity = info.get("severity", "info")
        info["color"] = SEVERITY_COLORS.get(severity, "#888")
        info["icon"] = SEVERITY_ICONS.get(severity, "i")
        return info

    # Handle ErrorCode_* registers dynamically
    if ":" in label:
        source_label, bit_name = label.rsplit(":", 1)

        if source_label in ERRORCODE_CHANNELS:
            # Extract bit number
            try:
                bit_num = int(bit_name.replace("b", ""))
            except ValueError:
                bit_num = -1

            channel = ERRORCODE_CHANNELS[source_label]

            if bit_num in ERRORCODE_BITS:
                bit_info = ERRORCODE_BITS[bit_num]
                severity = bit_info["severity"]
                return {
                    "name": f"{channel}: {bit_info['name']}",
                    "severity": severity,
                    "description": f"{bit_info['name']} error on {channel} channel",
                    "action": "Check controller display for details. May require calibration or service.",
                    "color": SEVERITY_COLORS.get(severity, "#888"),
                    "icon": SEVERITY_ICONS.get(severity, "i"),
                }
            else:
                # Unknown bit in ErrorCode register
                return {
                    "name": f"{channel}: Error Bit {bit_num}",
                    "severity": "warning",
                    "description": f"Error condition on {channel} channel (bit {bit_num})",
                    "action": "Check controller display for details.",
                    "color": SEVERITY_COLORS.get("warning", "#ff9800"),
                    "icon": SEVERITY_ICONS.get("warning", "!"),
                }

    # Generic fallback for completely unknown alarms
    return {
        "name": label,
        "severity": "warning",
        "description": "Alarm condition detected",
        "action": "Check controller display for details.",
        "color": SEVERITY_COLORS.get("warning", "#ff9800"),
        "icon": SEVERITY_ICONS.get("warning", "!"),
    }


def clean_system_name(raw_name):
    """Clean up system name by removing null characters and extra data"""
    if not raw_name:
        return ""

    # Remove null characters and split by common delimiters
    cleaned = raw_name.replace('\x00', ' ').strip()

    # Often the format is: "Pool name <nulls> version <nulls> date"
    # Take only the first meaningful part
    parts = [p.strip() for p in cleaned.split() if p.strip()]
    if parts:
        # Return first non-version part (version usually starts with 'v')
        for part in parts:
            if not part.startswith('v') and not part.replace('.', '').replace('-', '').isdigit():
                return part
        return parts[0]

    return cleaned
