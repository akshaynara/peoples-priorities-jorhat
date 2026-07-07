"""
Central config. Detects whether real API keys are present and flips
each service to live mode INDEPENDENTLY — Gemini extraction can go live
the moment GEMINI_API_KEY is set, without waiting for Maps too, and vice
versa. This lets you upgrade one piece at a time instead of all-or-nothing.
"""

import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# Independent flags — each service checks its own key
GEMINI_LIVE = bool(GEMINI_API_KEY)
MAPS_LIVE = bool(GOOGLE_MAPS_API_KEY)

# Kept for backward compatibility / status endpoint: True only if BOTH are live
DEMO_MODE = not (GEMINI_LIVE and MAPS_LIVE)

print(
    f"[config] Extraction: {'LIVE (Gemini)' if GEMINI_LIVE else 'DEMO (rule-based)'} | "
    f"Geocoding: {'LIVE (Google Maps)' if MAPS_LIVE else 'DEMO (local gazetteer)'}"
)
