# People's Priorities — Jorhat Constituency

AI platform for consolidating citizen development requests and ranking them
against real infrastructure data, built for the **Code for Communities
Hackathon 2026**, Track 1: *People's Priorities*.

**Target constituency:** Jorhat, Assam (MP: Gaurav Gogoi)

## Live links

- **Citizen submission page:** https://peoples-priorities-jorha-20747.web.app/index.html
- **MP Dashboard:** https://peoples-priorities-jorha-20747.web.app/dashboard.html
- **Backend API:** https://peoples-priorities-backend-393184150839.asia-south1.run.app
- **Source code:** https://github.com/akshaynara/peoples-priorities-jorhat

## The problem

MPs receive development requests through public meetings, letters, social
media, and grievance portals, with no objective way to consolidate citizen
feedback, spot recurring needs, or weigh competing proposals against real
demand data.

## What this does

Citizens submit development requests via voice or text, in any language.
The system:
1. Extracts structured signals (category, urgency, location, summary) using **Gemini**
2. Geocodes the location using **Google Maps** (with a curated local gazetteer as a fallback/precision layer for informal area names Maps doesn't resolve well)
3. Clusters submissions reporting the same issue, using real distance (not naive grid rounding), so many citizens reporting one incident register as one high-confidence priority — not fragments
4. Scores each cluster with a **transparent, inspectable formula** — not a black-box LLM ranking — combining report volume, urgency, and (for school-related requests) a real enrollment/infrastructure gap benchmarked against actual Jorhat district data
5. Surfaces a ranked, mapped priority list for the MP's office

## Architecture

```
Citizen (voice/text)
        |
        v
Browser Speech-to-Text (voice, free, Chrome-native)
        |
        v
extraction.py --> Gemini (gemini-2.5-flash-lite)
        |          structured extraction: category, urgency, summary, location
        |          rate-limited + retried server-side for reliability
        v
extraction.py --> gazetteer (curated local areas) --> Google Maps Geocoding (fallback)
        |
        v
scoring.py --> distance-based clustering (same issue, many reporters -> 1 item)
        |
        v
scoring.py --> two-tier scoring:
        |        1) urgency tier (critical > high > medium > low) - matches
        |           real emergency/civic triage: a safety-critical report
        |           always outranks a routine one, regardless of category
        |        2) within the same tier, a transparent weighted formula:
        |           volume + urgency + (school-only) enrollment gap vs.
        |           real UDISE+ data + distance from nearest facility
        v
main.py (Flask, Cloud Run) --> /rankings --> MP Dashboard (Leaflet map + ranked list)
```

**Design decision worth noting:** Gemini is used only for structured
extraction — turning messy multilingual input into clean fields. The actual
prioritization decision is a deterministic, auditable formula, not an LLM
call. This means every ranking is explainable: the dashboard shows exactly
which factors (urgency / enrollment gap / distance) drove each score.

## Real data sources used

- **Jorhat district school aggregates** (1,033 schools, 48,376 students,
  pupil-teacher ratio 13 vs. Assam state average ~19-20) — Samagra Shiksha
  Axom, Government of Assam, citing UDISE+ 2024-25 data.
- **Individual school names, UDISE codes, and coordinates** — geocoded live
  via Google Maps Geocoding API against the UDISE+ school directory.
- Per-school enrollment/PTR figures used in the demo benchmark set are
  illustrative (not yet pulled from individual UDISE+ school records) —
  the district-level aggregates and the scoring methodology are real.

## Tech stack

- **AI/ML:** Gemini API (gemini-2.5-flash-lite) for structured extraction
- **Geospatial:** Google Maps Geocoding API, Leaflet/OpenStreetMap for the dashboard map
- **Backend:** Python, Flask, deployed on Cloud Run
- **Frontend:** Vanilla HTML/JS, deployed on Firebase Hosting
- **Voice input:** Browser-native Web Speech API (no additional cost/setup)

## Running locally

The backend runs in two modes, auto-detected from environment variables —
no code changes needed either way.

**Demo mode (zero API keys, rule-based extraction + local gazetteer):**
```bash
cd backend
pip install flask
python3 main.py
```

**Live mode (real Gemini + real Maps):**
```bash
cd backend
export GEMINI_API_KEY=your_key
export GOOGLE_MAPS_API_KEY=your_key
pip install -r requirements.txt
python3 main.py
```

Then open `frontend/index.html` and `frontend/dashboard.html` directly in
a browser (update the `API_BASE` constant near the top of each file's
`<script>` if pointing at a different backend than the deployed one).

**Smoke test** (scoring logic only, no API keys or server needed):
```bash
cd backend
python3 test_scoring_smoke.py
```

## Deployment

- **Backend:** `gcloud run deploy` from the `backend/` folder (see `Procfile`)
- **Frontend:** `firebase deploy --only hosting` from the project root (see `firebase.json`)

## Team

Solo build — Akshay Nara.
