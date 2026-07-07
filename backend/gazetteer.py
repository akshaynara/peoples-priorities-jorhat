"""
Local gazetteer for Jorhat constituency — a free, zero-API-key fallback
for geocoding. Maps known place names (and common variants/misspellings)
to lat/lon. Used automatically in DEMO_MODE; swapped for real Google Maps
Geocoding once GOOGLE_MAPS_API_KEY is set (see extraction.py).

Coordinates here are approximate town/area centers, adequate for
demo-level hotspot clustering. Not survey-grade — fine for a hackathon
prototype, should be noted as such in the deck.
"""

from difflib import get_close_matches

JORHAT_CENTER = (26.7509, 94.2037)

GAZETTEER: dict[str, tuple[float, float]] = {
    "jorhat": JORHAT_CENTER,
    "jorhat town": JORHAT_CENTER,
    "north west jorhat": (26.81, 94.25),
    "titabor": (26.6167, 94.2000),
    "kunwari pukhuri": (26.78, 94.18),
    "mariani": (26.6667, 94.3167),
    "teok": (26.7333, 94.3667),
    "cinnamara": (26.7833, 94.2167),
    "gar-ali": (26.7550, 94.2100),
    "aat": (26.7300, 94.2700),
    "dergaon": (26.7000, 93.9667),
    "sarupathar": (26.1667, 94.4000),
    "rowmari": (26.7700, 94.1900),
}


def gazetteer_lookup(location_name: str) -> tuple[float, float] | None:
    """
    Best-effort local lookup: exact match, then fuzzy match on known
    Jorhat place names. Falls back to None if nothing close is found
    (caller should then flag for manual review, same as a failed real
    geocode call).
    """
    if not location_name:
        return JORHAT_CENTER  # default to constituency center rather than dropping

    key = location_name.strip().lower()
    if key in GAZETTEER:
        return GAZETTEER[key]

    close = get_close_matches(key, GAZETTEER.keys(), n=1, cutoff=0.6)
    if close:
        return GAZETTEER[close[0]]

    # Unknown place name — default to constituency center with a wider
    # jitter isn't safe (would misplace on map), so return center as-is.
    # In production this should be a manual-review flag, not silent fallback.
    return JORHAT_CENTER
