# People's Priorities — Jorhat Constituency

AI platform for consolidating citizen development requests and ranking them
against real benchmark data (school enrollment, PTR, distance) for MP
decision-making. Built for Code for Communities Hackathon (Track 1).

**Target constituency:** Jorhat, Assam (MP: Gaurav Gogoi)

## Architecture

```
Citizen (voice/text/SMS)
        │
        ▼
Speech-to-Text (voice) ──► raw text
        │
        ▼
extraction.py ──► Gemini structured extraction
        │           (category, urgency, summary, location_name)
        ▼
extraction.py ──► Google Maps Geocoding
        │           (location_name -> lat/lon, biased to Jorhat)
        ▼
Firestore (submissions store)
        │
        ▼
scoring.py ──► cluster + TRANSPARENT weighted formula
        │        (volume + urgency + enrollment_gap + distance_gap
        │         vs. real UDISE+ benchmark data)
        ▼
main.py /rankings ──► MP dashboard (ranked list + map hotspots)
```

**Key design decision:** Gemini is used ONLY for structured extraction
(turning messy multilingual input into clean fields). The actual
prioritization is a transparent, auditable formula in `scoring.py` — not
an LLM black box. This directly targets the "AI doing real work, not
decorative" evaluation criterion, and lets you explain in the demo *exactly*
why item #1 outranked #2.

## Real data sources used

- **School enrollment/PTR:** Samagra Shiksha Axom, Govt. of Assam
  (https://ssa.assam.gov.in/resource/basic-data) — UDISE+ 2024-25.
  Jorhat district: 1,033 schools, 48,376 students, PTR 13 (vs. Assam state
  avg ~19-20).
- **School names/UDISE codes:** UDISE+ national directory.
- ⚠️ Individual school lat/lon in `benchmark_data.py` are PLACEHOLDERS —
  must be geocoded via `extraction.geocode_location()` before the demo.
  Individual school enrollment/PTR figures are also placeholders pending
  real per-school UDISE+ lookup (only district aggregates are confirmed real
  so far) — flag clearly in the deck which numbers are real vs. illustrative
  until replaced.

## Run it right now — zero API keys needed (demo mode)

The whole pipeline (extraction, geocoding, clustering, scoring, dashboard)
runs today with no keys at all, via a rule-based extractor and a local
Jorhat gazetteer (see config.py, extraction.py, gazetteer.py). The moment
you export GEMINI_API_KEY and GOOGLE_MAPS_API_KEY, the same code switches
to live Gemini + Maps automatically, no code changes.

```bash
cd backend
pip install flask
python main.py
```

Then open frontend/index.html in your browser (citizen intake, try voice
input, it uses the browser's built-in speech recognition, works in Chrome
with zero setup) and frontend/dashboard.html (MP dashboard with map, uses
free OpenStreetMap/Leaflet, no Google Maps key needed for display, only
for geocoding new free-text locations).

Submit a few requests on the intake page, then check the dashboard, it
auto-refreshes every 15s and shows ranked, mapped hotspots.

### Smoke test (backend logic only, fastest sanity check)
```bash
python test_scoring_smoke.py
```

## Run with live Gemini + Maps (once you have keys)

```bash
export GEMINI_API_KEY=...
export GOOGLE_MAPS_API_KEY=...
pip install -r requirements.txt
python main.py
```
Everything else, frontend, dashboard, scoring, is unchanged. config.py
auto-detects the keys and flips DEMO_MODE off.

## Real data sources used (confirm in your deck)

- Real: Jorhat district aggregates (1,033 schools, 48,376 students, PTR
  13 vs. Assam state avg ~19-20), Samagra Shiksha Axom, Govt. of Assam.
- Real: school names + UDISE codes for several Jorhat/NW Jorhat schools.
- Placeholder (label clearly in deck until replaced): individual school
  lat/lon and per-school enrollment/PTR in benchmark_data.py; the demo-mode
  gazetteer's area coordinates are approximate area centers, not survey-grade.

## Priority order for your remaining ~48 hours

1. Done today: data model, scoring engine, extraction (Gemini + free
   fallback), gazetteer, Cloud Run backend, citizen intake UI, MP dashboard
   with map, all built and smoke-tested, runs with zero keys.
2. Now: get GEMINI_API_KEY (free, AI Studio) and GOOGLE_MAPS_API_KEY
   (needs a card on file, $200/mo free credit), swap in, confirm one real
   /submit call works.
3. Geocode real lat/lon for the seed schools (replace placeholders), or
   leave the gazetteer as-is and clearly label it illustrative in the deck
   if time is tight, judges care more about the scoring logic being real.
4. Swap in-memory SUBMISSIONS for Firestore only if you want persistence
   across restarts, for a demo, in-memory is fine and simpler.
5. Add an SMS/WhatsApp intake path if time allows (Inclusivity, 15%
   weight), even a simple Twilio sandbox stub is enough for the deck.
6. Deploy backend to Cloud Run, frontend to Firebase Hosting.
7. Record demo video (3-5 min) and build the pitch deck.
8. Submit before 8 July, 11:59 PM IST, leave buffer, don't submit at 11:58.
