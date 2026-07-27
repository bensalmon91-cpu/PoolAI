"""
Plain-English interpretation and corrective-action advice for a Langelier
Saturation Index (LSI) reading.

Deliberately fully internalized - no Claude/Anthropic (or any other LLM) API
call anywhere in this module or its callers. The bands and corrective
actions are static, hand-authored pool-chemistry knowledge, not generated
text. Do not wire this up to brain/llm_analyzer.py or the server-side
ClaudeAPI PHP class - that was an explicit, considered decision (cost,
offline/cloud_enabled=off operation, and response-latency on an 800x480
kiosk touchscreen all favour a instant, free, local answer over a network
round trip for something this well-defined).

No Flask/DB imports here by design, matching langelier.py's style, so this
is trivially unit-testable and reusable from both the maintenance page
(after a fresh calculation) and the LSI history chart page (for the latest
reading).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

# Same +/-0.3 boundary already used for the chart's point-coloring bands
# (charts.py's lsi_chart_page) - keeping one canonical definition of
# "balanced" for both the text interpretation and the chart avoids the
# confusing experience of the two disagreeing about the same reading.
CORROSIVE_THRESHOLD = -0.3
SCALING_THRESHOLD = 0.3

_FACTOR_LABELS = {
    "A_tds": "TDS (total dissolved solids)",
    "B_temp": "water temperature",
    "C_calcium": "calcium hardness",
    "D_alkalinity": "total alkalinity",
}


@dataclass(frozen=True)
class LSIInterpretation:
    band: str  # "corrosive" | "balanced" | "scaling"
    headline: str
    description: str
    actions: List[str]
    dominant_factor: Optional[str] = None  # e.g. "calcium hardness"


def _dominant_factor(factors: Optional[Dict[str, float]]) -> Optional[str]:
    """Pick the factor with the largest magnitude as "most responsible" for
    pushing the index off balance, so the checklist can point at a specific
    thing to adjust rather than only giving generic advice. Not a rigorous
    sensitivity analysis (the four factors aren't on a shared scale by
    design), just a useful hint - the checklist below always lists the full
    set of relevant actions regardless of this pick.
    """
    if not factors:
        return None
    try:
        biggest = max(factors, key=lambda k: abs(factors[k]))
    except (ValueError, TypeError):
        return None
    return _FACTOR_LABELS.get(biggest)


def interpret_lsi(lsi_value: float, factors: Optional[Dict[str, float]] = None) -> LSIInterpretation:
    """Interpret an LSI value into a plain-English verdict and a corrective
    action checklist. `factors` is the optional {"A_tds", "B_temp",
    "C_calcium", "D_alkalinity"} dict from LSIResult.factors - when given,
    the returned interpretation names the largest contributor.
    """
    dominant = _dominant_factor(factors)

    if lsi_value < CORROSIVE_THRESHOLD:
        return LSIInterpretation(
            band="corrosive",
            headline="Corrosive - water is under-saturated",
            description=(
                "The water is aggressive and can etch grout, metal fittings, "
                "heat exchangers, and plaster/render surfaces over time."
            ),
            actions=[
                "Raise pH toward the 7.2-7.6 target range",
                "Raise total alkalinity if it is low",
                "Raise calcium hardness if it is low",
                "Retest after each adjustment before making another change",
            ],
            dominant_factor=dominant,
        )

    if lsi_value > SCALING_THRESHOLD:
        return LSIInterpretation(
            band="scaling",
            headline="Scaling - water is over-saturated",
            description=(
                "The water is prone to depositing scale on tiles, heaters, "
                "and pipework, and can cause cloudiness."
            ),
            actions=[
                "Lower pH toward the 7.2-7.6 target range",
                "Lower total alkalinity if it is high",
                "Dilute with fresh water (partial drain/refill) if calcium "
                "hardness or TDS is elevated",
                "Retest after each adjustment before making another change",
            ],
            dominant_factor=dominant,
        )

    return LSIInterpretation(
        band="balanced",
        headline="Balanced",
        description=(
            "Water chemistry is in the balanced range - low risk of both "
            "scaling and corrosion."
        ),
        actions=[
            "Maintain the current dosing schedule",
            "Retest per your normal maintenance policy",
        ],
        dominant_factor=None,
    )
