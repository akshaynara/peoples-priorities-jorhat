"""
Gemini extraction module — WITH zero-key fallback for demo mode.

Role in the pipeline: turn messy, multilingual citizen input (voice
transcript or text) into STRUCTURED SIGNALS ONLY — category, urgency,
location, one-line summary. This is deliberately narrow. The actual ranking
decision happens in scoring.py's transparent formula, not here — that split
is what keeps the "AI/Technical Execution" story credible (extraction is an
LLM's job; prioritization is an auditable algorithm's job).

DEMO MODE: if GEMINI_API_KEY / GOOGLE_MAPS_API_KEY are not set, this module
automatically falls back to a rule-based keyword extractor and a local
gazetteer (see gazetteer.py) — so the full pipeline runs and demos TODAY,
with zero external dependencies. The moment real keys are exported, the
same function calls switch to live Gemini + Maps automatically. No code
changes needed at call sites (main.py doesn't know or care which mode
is active).
"""

import json
import re
import threading
import time

from models import Category, Urgency, SubmissionChannel
from config import GEMINI_LIVE, MAPS_LIVE, GEMINI_API_KEY, GOOGLE_MAPS_API_KEY
from gazetteer import gazetteer_lookup, GAZETTEER

MODEL_NAME = "gemini-2.5-flash-lite"  # higher free-tier rate limit (~30 req/min vs ~15 for flash)

# --- Proactive rate limiter -----------------------------------------------
# Free-tier Gemini allows ~30 requests/minute. Rather than firing immediately
# and reactively retrying on a 429/503 (which can still collide under
# concurrent or rapid submissions), this enforces a minimum spacing BEFORE
# every call — so the server simply never sends requests fast enough to be
# rejected. Trades a small, predictable delay (up to ~2.2s) for near-zero
# random failures. Thread-safe: works correctly even with gunicorn's
# multiple worker threads on a single Cloud Run instance.
_rate_limit_lock = threading.Lock()
_last_gemini_call_time = 0.0
_MIN_INTERVAL_SECONDS = 2.2  # ~27 req/min, comfortably under the ~30/min free-tier ceiling


def _wait_for_rate_limit_slot():
    global _last_gemini_call_time
    with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_gemini_call_time
        if elapsed < _MIN_INTERVAL_SECONDS:
            time.sleep(_MIN_INTERVAL_SECONDS - elapsed)
        _last_gemini_call_time = time.monotonic()

EXTRACTION_SYSTEM_PROMPT = """You are a structured data extractor for a civic
development-priorities platform serving Jorhat constituency, Assam, India.

You will receive a citizen's raw submission (may be in Hindi, Assamese, or
English, possibly a voice transcript with disfluencies). Extract ONLY the
following fields and return STRICT JSON with no markdown, no preamble:

{
  "category": one of ["school_upgrade", "vocational_centre", "road_infrastructure",
                       "health_facility", "water_sanitation", "other"],
  "urgency": one of ["low", "medium", "high", "critical"],
  "summary": "one clear sentence in English summarizing the request",
  "location_name": "best-guess place name mentioned (village/area/landmark), or empty string",
  "language_detected": "ISO 639-1 code, e.g. hi, as, en"
}

Rules:
- Infer urgency from language cues (e.g. "roof is collapsing" = critical;
  "would be nice to have" = low). Do not default everything to medium.
- ANY report involving immediate danger to life or safety — violence,
  attacks, terrorism, active fires, structural collapse, medical
  emergencies in progress — MUST be classified "critical", regardless of
  category. This overrides all other urgency cues.
- If the submission clearly doesn't fit a category, use "other" — do not force-fit.
- location_name should be a place, not a person or facility name, unless no
  place is mentioned at all.
- Return ONLY the JSON object. No explanation, no code fences.
"""


# --- Rule-based fallback (DEMO_MODE, zero API keys) ---------------------

_CATEGORY_KEYWORDS = {
    Category.SCHOOL_UPGRADE: [
        "school", "teacher", "classroom", "student", "vidyalaya", "shiksha",
        "padhai", "vidyarthi", "hs", "primary", "ptr",
    ],
    Category.VOCATIONAL_CENTRE: [
        "vocational", "training centre", "skill", "iti", "employment",
    ],
    Category.ROAD_INFRASTRUCTURE: [
        "road", "bridge", "pothole", "sadak", "pul", "highway", "street",
    ],
    Category.HEALTH_FACILITY: [
        "hospital", "health", "phc", "chc", "clinic", "doctor", "medicine",
        "aspatal", "dawai",
    ],
    Category.WATER_SANITATION: [
        "water", "sanitation", "drainage", "toilet", "pani", "sewage",
        "flood", "drinking water",
    ],
}

_CRITICAL_KEYWORDS = ["collapsing", "collapsed", "urgent", "emergency", "danger",
                      "girne wala", "toot gaya", "unsafe", "flooding",
                      "attack", "terror", "fire", "aag", "bomb", "shooting",
                      "violence", "hamla", "aatank"]
_HIGH_KEYWORDS = ["overcrowded", "shortage", "lack of", "need", "zaroorat",
                  "kami", "problem", "issue", "broken"]
_LOW_KEYWORDS = ["would be nice", "suggestion", "consider", "future",
                 "eventually", "acha hoga"]


def _rule_based_extract(raw_text: str) -> dict:
    """
    Free, zero-key fallback extractor. Keyword-matches category and urgency,
    and pulls a location name via gazetteer substring matching. Good enough
    to demo the full pipeline end-to-end; swapped for Gemini automatically
    once GEMINI_API_KEY is set.
    """
    text_lower = raw_text.lower()

    best_category, best_hits = Category.OTHER, 0
    for category, keywords in _CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits > best_hits:
            best_category, best_hits = category, hits

    if any(kw in text_lower for kw in _CRITICAL_KEYWORDS):
        urgency = Urgency.CRITICAL
    elif any(kw in text_lower for kw in _HIGH_KEYWORDS):
        urgency = Urgency.HIGH
    elif any(kw in text_lower for kw in _LOW_KEYWORDS):
        urgency = Urgency.LOW
    else:
        urgency = Urgency.MEDIUM

    # Check longest place names first so "north west jorhat" matches before
    # the generic "jorhat" substring within it
    location_name = ""
    for place in sorted(GAZETTEER.keys(), key=len, reverse=True):
        if place in text_lower:
            location_name = place.title()
            break

    language = "hi" if re.search(r"[\u0900-\u097F]", raw_text) else "en"

    summary = raw_text.strip()
    if len(summary) > 140:
        summary = summary[:137] + "..."

    return {
        "category": best_category,
        "urgency": urgency,
        "summary": summary,
        "location_name": location_name,
        "language": language,
    }


def _gemini_extract(raw_text: str, channel: SubmissionChannel) -> dict:
    """
    Live Gemini call — only used when GEMINI_API_KEY is set.

    Waits for a rate-limit slot before calling (see _wait_for_rate_limit_slot
    above), and retries with backoff up to 2 extra times if Google's actual
    limit turns out stricter than our conservative estimate. This is what
    makes submissions feel seamless to the end user instead of surfacing
    raw 429/503 errors.
    """
    from google import genai  # imported lazily so DEMO_MODE never needs this installed

    client = genai.Client(api_key=GEMINI_API_KEY)
    last_error = None

    for attempt in range(3):
        _wait_for_rate_limit_slot()
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=f"{EXTRACTION_SYSTEM_PROMPT}\n\nSubmission (via {channel.value}):\n{raw_text}",
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.strip("`").replace("json", "", 1).strip()

            parsed = json.loads(text)
            return {
                "category": Category(parsed.get("category", "other")),
                "urgency": Urgency(parsed.get("urgency", "medium")),
                "summary": parsed.get("summary", ""),
                "location_name": parsed.get("location_name", ""),
                "language": parsed.get("language_detected", "en"),
            }
        except Exception as e:
            last_error = e
            error_text = str(e).lower()
            is_rate_limit = "429" in error_text or "resource_exhausted" in error_text or "quota" in error_text
            if is_rate_limit and attempt < 2:
                time.sleep(3 * (attempt + 1))  # 3s, then 6s
                continue
            raise  # non-rate-limit error, or out of retries — surface it

    raise last_error


def extract_submission_fields(raw_text: str, channel: SubmissionChannel) -> dict:
    """
    Public entry point used by main.py. Routes to live Gemini extraction
    if GEMINI_API_KEY is set, otherwise the free rule-based fallback.
    Independent of whether the Maps key is set.
    """
    if GEMINI_LIVE:
        return _gemini_extract(raw_text, channel)
    return _rule_based_extract(raw_text)


def geocode_location(location_name: str, ward: str = "Jorhat, Assam") -> tuple[float, float] | None:
    """
    Resolve a free-text location name to lat/lon.

    Checks the local gazetteer FIRST, even in live mode. This matters
    because several real Jorhat sub-areas used in citizen submissions
    (e.g. "North West Jorhat") are informal names without a precise
    official Google Maps entry — Maps resolves them to the same broad
    town-center centroid as an empty query, which collapses distinct
    submissions onto one map point. The gazetteer's curated offsets keep
    known local areas visually distinct on the map. Google Maps is used
    as the fallback for any place name outside the curated list (e.g. a
    specific school or landmark Gemini extracts that we haven't mapped).
    """
    from gazetteer import GAZETTEER as _GAZ

    key = (location_name or "").strip().lower()
    if key in _GAZ:
        return _GAZ[key]

    if not MAPS_LIVE:
        return gazetteer_lookup(location_name)

    import googlemaps  # imported lazily; only needed in live mode

    gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
    query = f"{location_name}, {ward}" if location_name else ward
    result = gmaps.geocode(query)

    if not result:
        return gazetteer_lookup(location_name)  # fall back rather than dropping the submission

    loc = result[0]["geometry"]["location"]
    return loc["lat"], loc["lng"]
