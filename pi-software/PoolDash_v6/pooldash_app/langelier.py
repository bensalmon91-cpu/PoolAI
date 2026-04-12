"""
Standalone Langelier Saturation Index (LSI) calculator module.

Designed to be imported by PoolAIssistant or any other Python code.
No Flask/Dash dependencies.

Notes:
- Uses the "pool/spa industry" approximation:
    pHs = (9.3 + A + B) - (C + D)
    LSI = pH - pHs

Where:
    A = (log10(TDS) - 1) / 10
    B = -13.12*log10(T_K) + 34.55
    C = log10(Ca hardness as CaCO3) - 0.4
    D = log10(Alkalinity as CaCO3)

- Temperature must be in C (converted internally to Kelvin).
- Calcium hardness and total alkalinity should be in mg/L as CaCO3.
- TDS in mg/L.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log10
from typing import Dict, Any


@dataclass(frozen=True)
class LSIInputs:
    """Inputs for LSI calculation."""

    ph: float
    temperature_c: float
    calcium_hardness_mgL_as_CaCO3: float
    total_alkalinity_mgL_as_CaCO3: float
    tds_mgL: float = 1000.0


@dataclass(frozen=True)
class LSIResult:
    """Result including LSI, saturation pH, and factors."""

    lsi: float
    ph_saturation: float
    factors: Dict[str, float]
    inputs: LSIInputs


def _require_positive(name: str, value: float, min_value: float = 0.000001) -> None:
    if value is None:
        raise ValueError(f"{name} must not be None")
    if value <= min_value:
        raise ValueError(f"{name} must be > {min_value}. Got {value!r}")


def _require_ph(name: str, value: float) -> None:
    if value is None:
        raise ValueError(f"{name} must not be None")
    if not (0.0 < value < 14.0):
        raise ValueError(f"{name} must be between 0 and 14. Got {value!r}")


def factor_A_tds(tds_mgL: float) -> float:
    """A = (log10(TDS) - 1) / 10"""
    _require_positive("tds_mgL", tds_mgL)
    return (log10(tds_mgL) - 1.0) / 10.0


def factor_B_temperature(temperature_c: float) -> float:
    """B = -13.12 * log10(T_K) + 34.55"""
    temperature_k = temperature_c + 273.15
    _require_positive("temperature_k", temperature_k)
    return -13.12 * log10(temperature_k) + 34.55


def factor_C_calcium(calcium_hardness_mgL_as_CaCO3: float) -> float:
    """C = log10(Ca hardness as CaCO3) - 0.4"""
    _require_positive("calcium_hardness_mgL_as_CaCO3", calcium_hardness_mgL_as_CaCO3)
    return log10(calcium_hardness_mgL_as_CaCO3) - 0.4


def factor_D_alkalinity(total_alkalinity_mgL_as_CaCO3: float) -> float:
    """D = log10(Alkalinity as CaCO3)"""
    _require_positive("total_alkalinity_mgL_as_CaCO3", total_alkalinity_mgL_as_CaCO3)
    return log10(total_alkalinity_mgL_as_CaCO3)


def saturation_ph(
    temperature_c: float,
    calcium_hardness_mgL_as_CaCO3: float,
    total_alkalinity_mgL_as_CaCO3: float,
    tds_mgL: float = 1000.0,
) -> Dict[str, Any]:
    """Returns pHs plus the factors used."""
    A = factor_A_tds(tds_mgL)
    B = factor_B_temperature(temperature_c)
    C = factor_C_calcium(calcium_hardness_mgL_as_CaCO3)
    D = factor_D_alkalinity(total_alkalinity_mgL_as_CaCO3)

    phs = (9.3 + A + B) - (C + D)

    return {
        "ph_saturation": phs,
        "factors": {
            "A_tds": A,
            "B_temp": B,
            "C_calcium": C,
            "D_alkalinity": D,
        },
    }


def lsi(inputs: LSIInputs) -> LSIResult:
    """Compute LSI from inputs and return a structured result."""
    _require_ph("ph", inputs.ph)

    out = saturation_ph(
        temperature_c=inputs.temperature_c,
        calcium_hardness_mgL_as_CaCO3=inputs.calcium_hardness_mgL_as_CaCO3,
        total_alkalinity_mgL_as_CaCO3=inputs.total_alkalinity_mgL_as_CaCO3,
        tds_mgL=inputs.tds_mgL,
    )

    phs = float(out["ph_saturation"])
    lsi_value = inputs.ph - phs

    return LSIResult(
        lsi=lsi_value,
        ph_saturation=phs,
        factors=dict(out["factors"]),
        inputs=inputs,
    )


def lsi_from_values(
    ph: float,
    temperature_c: float,
    calcium_hardness_mgL_as_CaCO3: float,
    total_alkalinity_mgL_as_CaCO3: float,
    tds_mgL: float = 1000.0,
) -> LSIResult:
    """Convenience wrapper if you do not want to construct LSIInputs."""
    return lsi(
        LSIInputs(
            ph=ph,
            temperature_c=temperature_c,
            calcium_hardness_mgL_as_CaCO3=calcium_hardness_mgL_as_CaCO3,
            total_alkalinity_mgL_as_CaCO3=total_alkalinity_mgL_as_CaCO3,
            tds_mgL=tds_mgL,
        )
    )
